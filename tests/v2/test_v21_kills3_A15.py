"""V2.1 (owner B-03, batch A15): aisef2/app/review_verify.py — `anchor` and `reproducer_contract`.

Who reads what these functions write, and what each reader relies on (the ANCHORED reason, the UNANCHORED /
CONTRADICTS_APPROVED reasons and the UNVERIFIABLE reasons all reach the journaled statement of a finding —
`review_verify.detail`, the gate row's detail, RUN.json sessions[].findings[]):

* the developer, in the retry prompt (feedback.retry_feedback prints a blocked row's detail verbatim), reads the
  ANCHORED reason: which clause, which approved outcome, which approved contracts;
* the operator triaging a finding that did not block reads the others. The status is the machine-read class, but ONE
  status covers several documented causes (the module docstring lists five for UNANCHORED, two for CONTRADICTS_APPROVED,
  six for UNVERIFIABLE), and the reason is the only carrier of which one applies. So the reader relies on the
  identifying elements (the clause, the subject locator, the keys, the contract ids, the outcome) and on the cause
  class: asserted here by the shortest phrase naming the cause, never a whole sentence and never a lead-in label.

What is deliberately NOT pinned: lead-in labels ('clause ', 'the subject '), punctuation, and the order of a list
printed for a person (`sorted(product_roots)`): nothing reads them, and their audit is recorded with the batch."""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle  # noqa: E402
from aisef2.app import review_verify as V  # noqa: E402
from aisef2.arch.enums import ObligationRole, Polarity, SubjectAbsence, SubjectKind  # noqa: E402
from aisef2.plan.obligation import EXPECTED_AT_PARENT, NOT_PREREGISTERED, Plan, PlanObligation  # noqa: E402
from aisef2.probe import catalog  # noqa: E402
from aisef2.product.approval import ContractApproval, Requirement  # noqa: E402
from aisef2.product.compiler import ProbeRef, compile_spec  # noqa: E402
from aisef2.product.contract import BehaviorContract, Subject  # noqa: E402

APP = "app:__main__"
LONG = "x" * 250       # an approved outcome the 200-character cut of the reason lands inside
#: (criterion, contract, clause, stimulus, observable) in the plan's order — the contracts of clauses 1.2 and 4.1 are
#: listed out of alphabetical order (BC-b before BC-a, L-b before L-a)
ROWS = (
    ("C1", "BC-b", "1.2", {"argv": ["a1"]}, {"exit_code": 2, "within_s": 5}),
    ("C2", "BC-a", "1.2", {"argv": ["a2"]}, {"exit_code": 2, "within_s": 5}),
    ("C3", "BC-c", "2.1", {"argv": ["b1"]}, {"exit_code": 0, "within_s": 5}),
    ("C4", "BC-d", "2.1", {"argv": ["b2"]}, {"exit_code": 2, "within_s": 5}),
    ("C5", "L-b", "4.1", {"argv": ["c1"]}, {"stdout": LONG, "within_s": 5}),
    ("C6", "L-a", "4.1", {"argv": ["c2"]}, {"stdout": LONG, "within_s": 5}),
)


def _project() -> bundle.Project:
    req = Requirement.create(id="R-X", text="the calculator command", source="docs/requirements.md §1")
    contracts = [BehaviorContract.create(id=bid, requirement_ids=(req.id,), subject=Subject(SubjectKind.CLI_INVOCATION, APP),
                                         stimulus=stim, observable=obs, polarity=Polarity.MUST_HOLD,
                                         subject_absence=SubjectAbsence.REQUIRES_SUBJECT, rationale="the example")
                 for _, bid, _, stim, obs in ROWS]
    approvals = [ContractApproval(req.id, req.requirement_hash, c.id, c.contract_hash, "human:fixture-owner", 1.0, ())
                 for c in contracts]
    e = catalog.active()[SubjectKind.CLI_INVOCATION]
    probes = {SubjectKind.CLI_INVOCATION: ProbeRef(e.probe_id, e.probe_digest)}
    spec = {c.id: compile_spec(c, requirements={req.id: req}, approvals=approvals, probes=probes).id for c in contracts}
    plan = Plan.create(id="PLAN-A15", baseline="0" * 40, plan_quality_policy=NOT_PREREGISTERED, obligations=tuple(
        PlanObligation(cid, spec[bid], "S1", ObligationRole.INTRODUCE, EXPECTED_AT_PARENT[ObligationRole.INTRODUCE], (),
                       f"S1 introduces {cid}") for cid, bid, *_ in ROWS))
    facts = {cid: {"requirement": req.id, "section": "§1", "clause": clause, "clause_text": "it behaves",
                   "subject": "python -m app"} for cid, _, clause, *_ in ROWS}
    doc = "# Calc\n"
    return bundle.load(bundle.dump(
        name="calc", description="A calculator command.", requirements_path="docs/requirements.md",
        requirements_sha256=hashlib.sha256(doc.encode()).hexdigest(), product_roots=("app", "tests"), requirements=(req,),
        contracts=contracts, approvals=approvals, plan=plan, facts=facts,
        stories={"S1": {"depends_on": [], "tests": ["tests/test_cli.py"]}}))


PROJECT = _project()


def finding(clause: str, stimulus: dict, observable: dict, locator: str = APP, kind: str = "cli_invocation") -> dict:
    return {"id": "F1", "severity": "high", "summary": "the command is wrong",
            "reproducer": {"clause": clause, "subject": {"kind": kind, "locator": locator}, "stimulus": stimulus,
                           "observable": observable}}


def anchor(f: dict) -> V.Anchor:
    return V.anchor(f, PROJECT)


def refusal(f: dict) -> V.Verification:
    """verify() on a reproducer the kernel refuses to read: it answers before any probe, checkout or process."""
    v = V.verify(f, requirements=PROJECT.requirements, product_roots=PROJECT.product_roots, root="unused",
                 revision="0" * 40, timeout_s=1, interpreter=sys.executable)
    assert v.status == V.UNVERIFIABLE and v.probe is None, v
    return v


def has_token(text: str, s: str) -> bool:
    """`s` stands in `text` whole: no identifier character (letter, digit, `_`, `.`, `-`) touches it on either side."""
    return re.search(rf"(?<![\w.-]){re.escape(s)}(?![\w.-])", text) is not None


def outcome_in(reason: str) -> dict:
    """The JSON object a reason carries (the outcome it states), read as data: spacing and key order are not promised."""
    value, _ = json.JSONDecoder().raw_decode(reason[reason.index("{"):])
    return value


class AnchoredReason(unittest.TestCase):
    """The reason of an ANCHORED finding — the only anchor that blocks, so what the developer's retry prompt carries —
    names the clause, says that the JSON is that clause's approved outcome, and names each approved contract that
    shows it, each as a token of its own (the statement carries `anchor` and `anchor_why`, never `contracts`: the ids
    exist in the text only). Pins aisef2/app/review_verify.py::anchor [48, 49]."""

    def test_the_reason_names_the_clause_the_approved_outcome_and_the_contracts(self):
        a = anchor(finding("R-X/1.2", {"argv": ["n"]}, {"exit_code": 2, "within_s": 5}))
        self.assertEqual(a.status, V.ANCHORED)
        self.assertTrue(has_token(a.reason, "R-X/1.2"), a.reason)
        self.assertEqual(outcome_in(a.reason), {"exit_code": 2})
        self.assertIn("approved outcome", a.reason)
        self.assertEqual(set(a.contracts), {"BC-a", "BC-b"})       # the loop below is not vacuous
        for cid in a.contracts:
            self.assertTrue(has_token(a.reason, cid), (cid, a.reason))

    def test_each_contract_stays_a_token_when_a_long_outcome_is_cut(self):
        """The outcome is cut at 200 characters, inside the string: whatever follows must still start a new token."""
        a = anchor(finding("R-X/4.1", {"argv": ["n"]}, {"stdout": LONG, "within_s": 5}))
        self.assertEqual((a.status, set(a.contracts)), (V.ANCHORED, {"L-a", "L-b"}))
        self.assertNotIn(LONG, a.reason)       # it is cut
        for cid in ("L-a", "L-b"):
            self.assertTrue(has_token(a.reason, cid), (cid, a.reason))


class AnchorContractsAreCanonical(unittest.TestCase):
    """`Anchor.contracts` (RUN.json sessions[].findings[].anchor.contracts) is the approved contracts' ids in
    alphabetical order, whatever order the plan lists the clause's obligations in; the reason lists them the same way.
    Pins aisef2/app/review_verify.py::anchor [33]."""

    def test_ids_are_alphabetical_though_the_plan_lists_b_before_a(self):
        self.assertEqual([r[1] for r in ROWS][:2], ["BC-b", "BC-a"])     # the fixture's premise: not alphabetical
        a = anchor(finding("R-X/1.2", {"argv": ["n"]}, {"exit_code": 2, "within_s": 5}))
        self.assertEqual(a.contracts, ("BC-a", "BC-b"))
        self.assertLess(a.reason.index("BC-a"), a.reason.index("BC-b"))


class UnanchoredCauses(unittest.TestCase):
    """UNANCHORED covers five documented causes (module docstring); the reason is the only carrier of which applies,
    next to the identifying elements of that cause — the clause, and the subject or the keys it concerns.
    Pins aisef2/app/review_verify.py::anchor [55, 58, 61, 63]."""

    def check(self, f: dict, phrase: str, *elements: str, contracts: tuple = ()):
        a = anchor(f)
        self.assertEqual((a.status, a.contracts), (V.UNANCHORED, contracts), a)
        self.assertIn(phrase, a.reason)
        for e in elements:
            self.assertTrue(has_token(a.reason, e), (e, a.reason))

    def test_no_approved_contract_declares_the_clause(self):
        self.check(finding("R-X/9.9", {"argv": ["n"]}, {"exit_code": 2, "within_s": 5}), "no approved contract", "R-X/9.9")

    def test_no_approved_contract_of_the_clause_observes_the_subject(self):
        """It names the locator the clause's contracts do not observe, and says so: a text that read `R-X/1.2 observes
        app:other` would state the opposite of what the status says."""
        self.check(finding("R-X/1.2", {"argv": ["n"]}, {"exit_code": 2, "within_s": 5}, locator="app:other"),
                   "no approved contract", "R-X/1.2", "app:other")

    def test_the_clause_s_contracts_do_not_observe_the_expected_keys(self):
        self.check(finding("R-X/1.2", {"argv": ["n"]}, {"stdout": "hi", "within_s": 5}), "do not observe", "R-X/1.2",
                   "stdout")

    def test_the_clause_s_contracts_expect_different_values_for_different_stimuli(self):
        self.check(finding("R-X/2.1", {"argv": ["n"]}, {"exit_code": 2, "within_s": 5}), "different values", "R-X/2.1",
                   contracts=("BC-c", "BC-d"))


class ContradictedFindings(unittest.TestCase):
    """CONTRADICTS_APPROVED covers two documented causes: an approved contract decides the very stimulus otherwise
    (it names that contract and its outcome), or the clause's approved outcome is not the one the finding states (it
    names the clause and that outcome). Pins aisef2/app/review_verify.py::anchor [67, 70]."""

    def test_an_approved_contract_decides_the_stimulus_otherwise(self):
        a = anchor(finding("R-X/1.2", {"argv": ["a1"]}, {"exit_code": 3, "within_s": 5}))
        self.assertEqual((a.status, a.contracts), (V.CONTRADICTS_APPROVED, ("BC-b",)))
        self.assertTrue(has_token(a.reason, "BC-b"), a.reason)
        self.assertIn("decides this stimulus", a.reason)
        self.assertEqual(outcome_in(a.reason), {"exit_code": 2})    # what that contract approved, not the finding's 3

    def test_the_clause_s_approved_outcome_is_another(self):
        a = anchor(finding("R-X/1.2", {"argv": ["n"]}, {"exit_code": 3, "within_s": 5}))
        self.assertEqual((a.status, a.contracts), (V.CONTRADICTS_APPROVED, ("BC-a", "BC-b")))
        self.assertTrue(has_token(a.reason, "R-X/1.2"), a.reason)
        self.assertIn("approved outcome", a.reason)
        self.assertEqual(outcome_in(a.reason), {"exit_code": 2})    # the clause's approved outcome, not the finding's 3


class UnverifiableReproducers(unittest.TestCase):
    """UNVERIFIABLE is one status for every reason a reproducer cannot be run; the reason names the offending element
    and the cause. Pins aisef2/app/review_verify.py::reproducer_contract [30, 32, 39]."""

    def reproducer(self, **change) -> dict:
        f = finding("R-X/1.2", {"argv": ["n"]}, {"exit_code": 2, "within_s": 5})
        return {**f, "reproducer": {**f["reproducer"], **change}}

    def test_a_reproducer_with_a_key_too_many_is_refused_with_the_keys_it_holds_exactly(self):
        v = refusal(self.reproducer(extra=1))
        self.assertIn("holds exactly", v.reason)
        for key in V.REPRODUCER_KEYS:
            self.assertTrue(has_token(v.reason, key), (key, v.reason))

    def test_a_reproducer_with_a_key_missing_is_refused_naming_the_keys_it_must_hold(self):
        """The reason lists the grammar's keys, not the ones the reproducer happens to hold: the key it lacks is there."""
        f = self.reproducer()
        del f["reproducer"]["stimulus"]
        v = refusal(f)
        self.assertIn("holds exactly", v.reason)
        for key in V.REPRODUCER_KEYS:
            self.assertTrue(has_token(v.reason, key), (key, v.reason))

    def test_a_clause_of_no_requirement_is_refused_naming_the_clause(self):
        v = refusal(self.reproducer(clause="R-404/1"))
        self.assertTrue(has_token(v.reason, "R-404/1"), v.reason)
        self.assertIn("no requirement", v.reason)

    def test_a_subject_outside_the_product_is_refused_naming_it_and_the_product(self):
        v = refusal(self.reproducer(subject={"kind": "cli_invocation", "locator": "json:__main__"}))
        self.assertTrue(has_token(v.reason, "json:__main__"), v.reason)
        self.assertIn("not in the product", v.reason)
        for root in PROJECT.product_roots:
            self.assertTrue(has_token(v.reason, root), (root, v.reason))

    def test_a_subject_kind_nobody_declares_is_refused_naming_it(self):
        v = refusal(self.reproducer(subject={"kind": "cli", "locator": APP}))
        self.assertTrue(has_token(v.reason, "cli"), v.reason)      # the offending kind, not `cli_invocation` among others


if __name__ == "__main__":
    unittest.main()
