"""V2.1 (owner B-03, survivor audit batch A15): aisef2/app/review_verify.py::reproducer_contract — the reviewer's
prose never decides a verdict.

Requirement (module docstring, ADR-7): a finding is verified by the kernel's probe and anchored by the bundle's
approved contracts and sealed clause facts "only — never from the reviewer's text". The finding's `id` and the first
500 characters of its `summary` become the throw-away contract's id and rationale: prose no control path reads
(aisef2/product/contract.py, invariant I). The contract's hash is over UTF-8, which has no form for a lone surrogate
— what `json.loads` yields from a model's "\\ud800" — so, before the fix, a surrogate in that prose made
`BehaviorContract.create` raise, and `reproducer_contract` turned it into "the reproducer is not a contract":
UNVERIFIABLE / UNANCHORED whatever the reproducer says, silently (a surrogate at character 400..499 of the summary
reaches no journal row).

What a consumer relies on, and what these tests assert:

* verify() and anchor() answer for a finding with a lone surrogate in its id or summary exactly as they answer for
  the same finding without it, and a CONFIRMED + ANCHORED one blocks (`blocks`);
* text that already encodes keeps its contract hash: the contract equals the one built by hand from the same text;
* the form of the replacement is deterministic and documented: each lone surrogate is written as its escape;
* what is NOT prose stays refused with a cause: a lone surrogate in the reproducer itself (its stimulus) is not a
  contract, and verify() says so without running a probe.

Not covered here, on purpose (owner decisions / other modules): `detail()`'s 1500-character bound, and the journal's
own refusal of a surrogate in a journaled row (aisef2/journal)."""

from __future__ import annotations

import copy
import hashlib
import pathlib
import shutil
import sys
import tempfile
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
REFERENCE = ROOT / "tests/v2/fixtures/workloads/ledgerlock-reference/reference/ledgerlock"
#: the ends of the surrogate range, and the low surrogate `surrogateescape` makes of a stray 0x80 byte
LONE = ("\ud800", "\udbff", "\udc00", "\udc80", "\udfff")
#: characters next to the surrogate range, and wider ones: they encode, so their contract hash is the one it always was
ENCODABLE = ("퟿", "", "é", "漢字", "\U0001f600", "\U0010ffff", "\\ud800")


def _project() -> bundle.Project:
    """One requirement, one clause (1.2) whose two approved contracts, on two stimuli, both expect exit code 2."""
    req = Requirement.create(id="R-X", text="the calculator command", source="docs/requirements.md §1")
    contracts = [BehaviorContract.create(id=cid, requirement_ids=(req.id,), subject=Subject(SubjectKind.CLI_INVOCATION, APP),
                                         stimulus={"argv": [arg]}, observable={"exit_code": 2, "within_s": 5},
                                         polarity=Polarity.MUST_HOLD, subject_absence=SubjectAbsence.REQUIRES_SUBJECT,
                                         rationale="the example") for cid, arg in (("BC-a", "a1"), ("BC-b", "a2"))]
    approvals = [ContractApproval(req.id, req.requirement_hash, c.id, c.contract_hash, "human:fixture-owner", 1.0, ())
                 for c in contracts]
    e = catalog.active()[SubjectKind.CLI_INVOCATION]
    probes = {SubjectKind.CLI_INVOCATION: ProbeRef(e.probe_id, e.probe_digest)}
    spec = {c.id: compile_spec(c, requirements={req.id: req}, approvals=approvals, probes=probes).id for c in contracts}
    plan = Plan.create(id="PLAN-REPRODUCER", baseline="0" * 40, plan_quality_policy=NOT_PREREGISTERED, obligations=tuple(
        PlanObligation(f"C{n}", spec[c.id], "S1", ObligationRole.INTRODUCE, EXPECTED_AT_PARENT[ObligationRole.INTRODUCE],
                       (), f"S1 introduces C{n}") for n, c in enumerate(contracts, 1)))
    facts = {f"C{n}": {"requirement": req.id, "section": "§1", "clause": "1.2", "clause_text": "it behaves",
                       "subject": "python -m app"} for n in (1, 2)}
    doc = "# Calc\n"
    return bundle.load(bundle.dump(
        name="calc", description="A calculator command.", requirements_path="docs/requirements.md",
        requirements_sha256=hashlib.sha256(doc.encode()).hexdigest(), product_roots=("app", "tests"), requirements=(req,),
        contracts=contracts, approvals=approvals, plan=plan, facts=facts,
        stories={"S1": {"depends_on": [], "tests": ["tests/test_cli.py"]}}))


PROJECT = _project()


def finding(**over) -> dict:
    return {"id": "F1", "severity": "high", "summary": "the command is wrong",
            "reproducer": {"clause": "R-X/1.2", "subject": {"kind": "cli_invocation", "locator": APP},
                           "stimulus": {"argv": ["n"]}, "observable": {"exit_code": 2, "within_s": 5}}, **over}


def contract_of(f: dict):
    return V.reproducer_contract(f, PROJECT.requirements, PROJECT.product_roots)


def must(f: dict) -> BehaviorContract:
    c = contract_of(f)
    if not isinstance(c, BehaviorContract):
        raise AssertionError(f"the finding's reproducer is not a contract: {c}")
    return c


def by_hand(f: dict, *, id: str, rationale: str) -> BehaviorContract:
    """The contract the finding's reproducer states, built without review_verify's help."""
    r = f["reproducer"]
    return BehaviorContract.create(id=id, requirement_ids=("R-X",), subject=Subject(SubjectKind.CLI_INVOCATION, APP),
                                   stimulus=r["stimulus"], observable=r["observable"], polarity=Polarity.MUST_HOLD,
                                   subject_absence=SubjectAbsence.REQUIRES_SUBJECT, rationale=rationale)


def summaries(s: str) -> dict[str, str]:
    """`s` placed in a long summary: at its start, inside the first 400 characters, past the 400 the journal row keeps
    (450), on the last character the contract keeps (499), and just past it (500: never in the contract)."""
    return {f"at {k}": "a" * k + s + "a" * 100 for k in (0, 399, 450, 499, 500)}


class ProseDoesNotDecide(unittest.TestCase):
    """A lone surrogate in the finding's id or summary leaves its contract, anchor and blocking exactly as they are."""

    def setUp(self) -> None:
        self.clean = finding()
        must(self.clean)
        self.want = V.anchor(self.clean, PROJECT)
        self.assertEqual(self.want.status, V.ANCHORED, self.want)

    def check(self, f: dict) -> None:
        c = must(f)
        # the observation, the subject and the requirement are the reproducer's: the prose changed none of them
        base = must(self.clean)
        self.assertEqual((c.requirement_ids, c.subject, dict(c.stimulus), dict(c.observable), c.polarity, c.subject_absence),
                         (base.requirement_ids, base.subject, dict(base.stimulus), dict(base.observable), base.polarity,
                          base.subject_absence))
        a = V.anchor(f, PROJECT)
        self.assertEqual(a, self.want)
        confirmed = V.Verification(V.CONFIRMED, "probe refutes", "probe.cli_invocation", "REFUTED")
        self.assertTrue(V.blocks(confirmed, f, "fix-loop", "low", a))     # a confirmed, anchored finding blocks

    def test_a_lone_surrogate_in_the_summary(self):
        for lone in LONE:
            for where, summary in summaries(lone).items():
                with self.subTest(surrogate=hex(ord(lone)), where=where):
                    self.check(finding(summary=summary))

    def test_a_lone_surrogate_in_the_id(self):
        for lone in LONE:
            for fid in (lone, "x" + lone, lone + "x", "f" * 200 + lone):
                with self.subTest(surrogate=hex(ord(lone)), id_length=len(fid)):
                    self.check(finding(id=fid))

    def test_a_lone_surrogate_in_both(self):
        self.check(finding(id="x\ud800", summary="a" * 450 + "\udfff" + "a" * 100))

    def test_two_runs_give_one_contract(self):
        """Deterministic: the same finding is the same contract (and so the same spec) however often it is read."""
        f = finding(id="x\ud800", summary="y\udc80")
        self.assertEqual(must(f).contract_hash, must(copy.deepcopy(f)).contract_hash)


class EncodableTextKeepsItsHash(unittest.TestCase):
    """The fix changes nothing for text that already encodes: the contract is the one built from that text by hand."""

    def test_the_contract_hash_is_the_one_the_text_always_had(self):
        for ch in ENCODABLE:
            for f in (finding(id=f"F-{ch}-1", summary=f"it is {ch} wrong"),
                      finding(id=ch, summary=ch + "z" * 600)):
                with self.subTest(character=ascii(ch), id=len(f["id"]), summary=len(f["summary"])):
                    c = must(f)
                    want = by_hand(f, id=f"REVIEW-{f['id']}", rationale=f["summary"][:500])
                    self.assertEqual((c.id, c.rationale, c.contract_hash), (want.id, want.rationale, want.contract_hash))

    def test_the_defaults_are_unchanged(self):
        f = finding()
        del f["id"], f["summary"]
        c = must(f)
        want = by_hand(f, id="REVIEW-finding", rationale="")
        self.assertEqual((c.id, c.rationale, c.contract_hash), (want.id, want.rationale, want.contract_hash))


class TheReplacementIsDocumented(unittest.TestCase):
    """Each lone surrogate is written as its escape (`\\ud800`, what the model wrote in its JSON); nothing else moves."""

    def test_a_lone_surrogate_is_written_as_its_escape(self):
        c = must(finding(id="a\ud800b\udfffc", summary="x\udc80y"))
        self.assertEqual(c.id, "REVIEW-a\\ud800b\\udfffc")
        self.assertEqual(c.rationale, "x\\udc80y")
        want = by_hand(finding(), id=c.id, rationale=c.rationale)
        self.assertEqual(c.contract_hash, want.contract_hash)       # an ordinary contract of that text: nothing special

    def test_the_summary_is_cut_at_500_characters_before_it_is_written(self):
        c = must(finding(summary="a" * 499 + "\ud800" + "b" * 50))
        self.assertEqual(c.rationale, "a" * 499 + "\\ud800")


class ReproducerIsNotProse(unittest.TestCase):
    """A lone surrogate in what the reproducer observes is not prose: the reproducer is refused, naming the cause."""

    def test_a_surrogate_in_the_stimulus_is_refused_with_a_cause(self):
        f = finding()
        f["reproducer"]["stimulus"] = {"argv": ["n\ud800"]}
        c = contract_of(f)
        self.assertIsInstance(c, str)
        self.assertIn("not a contract", c)
        a = V.anchor(f, PROJECT)
        self.assertEqual((a.status, a.reason), (V.UNANCHORED, c))
        v = V.verify(f, requirements=PROJECT.requirements, product_roots=PROJECT.product_roots, root="unused",
                     revision="0" * 40, timeout_s=1, interpreter=sys.executable)    # refused before any probe or process
        self.assertEqual((v.status, v.probe, v.reason), (V.UNVERIFIABLE, None, c))


class VerifyIsUnmovedByProse(unittest.TestCase):
    """verify() on a real checkout (the LedgerLock reference, the kernel's cli probe): the verdict is the reproducer's."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        shutil.copytree(REFERENCE, self.root / "ledgerlock", ignore=shutil.ignore_patterns("__pycache__"))

    def verify(self, f: dict) -> V.Verification:
        return V.verify(f, requirements={"R-9": object()}, product_roots=("ledgerlock",), root=str(self.root),
                        revision="0" * 40, timeout_s=60, interpreter=sys.executable)

    @staticmethod
    def stated(exit_code: int, **over) -> dict:
        """R-9/3's reproducer: `snapshot` of a missing file exits 3 on the reference; the finding states `exit_code`."""
        return {"id": "L1", "severity": "high", "summary": "snapshot of a missing file", "reproducer": {
            "clause": "R-9/3", "subject": {"kind": "cli_invocation", "locator": "ledgerlock:__main__"},
            "stimulus": {"argv": ["snapshot", "<ws>/missing.jsonl"], "stdin": None, "workspace": {}, "pre": []},
            "observable": {"exit_code": exit_code, "within_s": 20}}, **over}

    def test_a_lone_surrogate_does_not_turn_a_confirmation_into_a_refusal(self):
        wrong = self.verify(self.stated(4))                  # the candidate exits 3: the stated 4 is refuted
        self.assertEqual((wrong.status, wrong.probe, wrong.observed), (V.CONFIRMED, "probe.cli_invocation", "REFUTED"))
        for over in ({"id": "L\ud800"}, {"summary": "a" * 450 + "\ud800" + "a" * 100}):
            with self.subTest(over={k: len(v) for k, v in over.items()}):
                self.assertEqual(self.verify(self.stated(4, **over)), wrong)

    def test_nor_a_non_reproduction(self):
        right = self.verify(self.stated(3))                  # the candidate does exit 3
        self.assertEqual((right.status, right.observed), (V.NOT_REPRODUCED, "SATISFIED"))
        self.assertEqual(self.verify(self.stated(3, id="L\udc80")), right)


if __name__ == "__main__":
    unittest.main()
