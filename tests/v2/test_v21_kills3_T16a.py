"""V2.1 (owner B-03, kills round 3, batch T16a): the survivors of aisef2/app/review_verify.py's mutation targets
SEVERITIES, _approved_by_clause, _canon, _scalars, _states, _stimulus and verify, each class named by the behaviour it
pins and the mutants it kills ("Pins aisef2/app/review_verify.py::target [index]", the index in the runner's mutant
list of the target).

What decides whether a reviewer's finding blocks is `anchor` (is the finding's expected outcome the cited clause's
approved outcome?) and `verify` (does the kernel's probe reproduce it?). The existing files (test_v21_review*.py) run
LedgerLock's real bundle, whose single-contract clauses all have integer outcomes and whose stimuli are spelled without
defaults; here `anchor` is driven over small hand-built projects (it reads only requirements, product_roots, approvals,
plan.obligations, facts, specs and contracts) so that both sides of each decision are exercised, and `verify` over the
paths on which no probe observation can be made — which must be a triage row (UNVERIFIABLE), never a crash.

Not tested here, by design: the sentence around an identifier (a reason holds its identifying element and the class of
its cause, never the wording)."""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import review_verify as V  # noqa: E402
from aisef2.app import settings  # noqa: E402
from aisef2.arch.enums import Polarity, SubjectAbsence, SubjectKind  # noqa: E402
from aisef2.product.contract import BehaviorContract, Subject  # noqa: E402
from tests.v2.test_app_run import SETTINGS  # noqa: E402

CLI = (SubjectKind.CLI_INVOCATION, "calc:__main__")
FN = (SubjectKind.PYTHON_CALLABLE, "calc:add")
FILE = (SubjectKind.FILE_ARTIFACT, "path:calc/out.txt")
APPROVED, UNAPPROVED, STALE, NO_SPEC, NO_CONTRACT = "approved", "unapproved", "stale", "no-spec", "no-contract"
CLAUSE = "R-1/1"
CONFIRMED = V.Verification(V.CONFIRMED, "the probe refutes it", "probe.x", "REFUTED")


def contract(cid: str, shape, stimulus: dict, observable: dict) -> BehaviorContract:
    kind, locator = shape
    return BehaviorContract.create(id=cid, requirement_ids=("R-1",), subject=Subject(kind, locator), stimulus=stimulus,
                                   observable={**observable, "within_s": 10}, polarity=Polarity.MUST_HOLD,
                                   subject_absence=SubjectAbsence.REQUIRES_SUBJECT, rationale=cid)


def project(*rows):
    """What `anchor` reads of a bundle.Project. A row is (contract, clause, the clause's text[, what binds it]); the
    default is an approval of exactly that contract (id and hash)."""
    approvals, obligations, facts, specs, contracts = [], [], {}, {}, {}
    for n, (c, clause, text, *how) in enumerate(rows):
        how = how[0] if how else APPROVED
        criterion, spec = f"C-{n}", f"PPS-{n}"
        obligations.append(SimpleNamespace(criterion_id=criterion, product_proof_spec_id=spec))
        facts[criterion] = {"clause": clause, "requirement": "R-1", "clause_text": text}
        if how != NO_SPEC:
            specs[spec] = SimpleNamespace(contract_id=c.id)
        if how != NO_CONTRACT:
            contracts[c.id] = c
        if how in (APPROVED, NO_SPEC, NO_CONTRACT):
            approvals.append(SimpleNamespace(contract_id=c.id, contract_hash=c.contract_hash))
        elif how == STALE:       # an approval of this contract's id at another content
            approvals.append(SimpleNamespace(contract_id=c.id, contract_hash="0" * 64))
    return SimpleNamespace(requirements={"R-1": object()}, product_roots=("calc",), approvals=tuple(approvals),
                           plan=SimpleNamespace(obligations=tuple(obligations)), facts=facts, specs=specs,
                           contracts=contracts)


def finding(stimulus: dict, observable: dict, shape=CLI, clause: str = CLAUSE) -> dict:
    kind, locator = shape
    return {"id": "F-1", "severity": "high", "summary": "what the reviewer says",
            "reproducer": {"clause": clause, "subject": {"kind": kind.value, "locator": locator},
                           "stimulus": stimulus, "observable": {**observable, "within_s": 10}}}


class SeverityScale(unittest.TestCase):
    """Pins aisef2/app/review_verify.py::SEVERITIES [3]. The scale is low < medium < high < critical: a finding
    declaring none the scale knows is `low` and meets no floor above low; `critical` meets every floor, itself
    included, and is a floor the settings accept (a floor of '' they refuse)."""

    SCALE = ("low", "medium", "high", "critical")

    def test_a_finding_declares_a_severity_on_the_scale_or_is_low(self):
        for declared, read in (("critical", "critical"), ("CRITICAL", "critical"), ("High", "high"), ("medium", "medium"),
                               ("", "low"), ("urgent", "low"), (None, "low")):
            with self.subTest(declared=declared):
                self.assertEqual(V.severity_of({"id": "x", "severity": declared}), read)
        self.assertEqual(V.severity_of({"id": "x"}), "low")

    def test_what_meets_a_floor(self):
        anchored = V.Anchor(V.ANCHORED, "the clause's outcome")

        def blocks(finding: dict, floor: str) -> bool:
            return V.blocks(CONFIRMED, finding, "fix-loop", floor, anchored)

        for finding in ({"id": "x"}, {"id": "x", "severity": ""}, {"id": "x", "severity": "urgent"}):
            with self.subTest(finding=finding):
                self.assertTrue(blocks(finding, "low"))
                for floor in ("medium", "high", "critical"):
                    self.assertFalse(blocks(finding, floor), floor)
        for floor in self.SCALE:
            self.assertTrue(blocks({"id": "x", "severity": "critical"}, floor), floor)
            self.assertTrue(blocks({"id": "x", "severity": "CRITICAL"}, floor), floor)
        self.assertFalse(blocks({"id": "x", "severity": "high"}, "critical"))

    def test_the_settings_accept_critical_as_a_floor_and_nothing_as_one(self):
        for floor in self.SCALE:
            with self.subTest(floor=floor):
                loaded = settings.load({**SETTINGS, "review": {"policy": "fix-loop", "min_severity": floor}})
                self.assertEqual(loaded.review["min_severity"], floor)
        for floor in ("", "urgent", None):
            with self.subTest(floor=floor), self.assertRaises(settings.SettingsError):
                settings.load({**SETTINGS, "review": {"policy": "fix-loop", "min_severity": floor}})


class ApprovedContractsOnly(unittest.TestCase):
    """Pins aisef2/app/review_verify.py::_approved_by_clause [6]. Anchoring decides from the bundle's approved
    contracts only: a contract the plan names but no approval binds — by id and by hash — never anchors, never shows a
    clause's outcome is constant, never contradicts, and is not a clause's declaration; an obligation whose spec or
    contract the project does not hold is no contract at all. (A loaded Project cannot hold such a row — `bundle.load`
    refuses it — so this is the guard of the public `anchor` for any project-shaped input.)"""

    TEXT = "exit 3 on an I/O error"
    GO = contract("BC-GO", CLI, {"argv": ["go"]}, {"exit_code": 3})
    AGAIN = finding({"argv": ["go", "again"]}, {"exit_code": 3})

    def test_a_contract_no_approval_binds_never_anchors(self):
        for how in (UNAPPROVED, STALE):
            with self.subTest(how=how):
                a = V.anchor(self.AGAIN, project((self.GO, CLAUSE, self.TEXT, how)))
                self.assertEqual((a.status, a.contracts), (V.UNANCHORED, ()))
        a = V.anchor(self.AGAIN, project((self.GO, CLAUSE, self.TEXT)))     # the same project once it is approved
        self.assertEqual((a.status, a.contracts), (V.ANCHORED, (self.GO.id,)))

    def test_an_unapproved_contract_does_not_show_a_clauses_outcome_is_constant(self):
        approved = contract("BC-P1", CLI, {"argv": ["go"]}, {"exit_code": 3})
        other = contract("BC-P2", CLI, {"argv": ["stop"]}, {"exit_code": 3})
        said = "the I/O failure code"        # no number: one contract does not show its outcome is the constant
        for how in (UNAPPROVED, STALE):
            with self.subTest(how=how):
                a = V.anchor(self.AGAIN, project((approved, CLAUSE, said), (other, CLAUSE, said, how)))
                self.assertEqual((a.status, a.contracts), (V.UNANCHORED, (approved.id,)))
        a = V.anchor(self.AGAIN, project((approved, CLAUSE, said), (other, CLAUSE, said)))   # approved: two stimuli
        self.assertEqual((a.status, a.contracts), (V.ANCHORED, (approved.id, other.id)))

    def test_an_unapproved_contract_decides_no_stimulus(self):
        other = contract("BC-OTHER", CLI, {"argv": ["other"]}, {"exit_code": 4})
        on_other = finding({"argv": ["other"]}, {"exit_code": 3})
        for how in (UNAPPROVED, STALE):
            with self.subTest(how=how):
                a = V.anchor(on_other, project((self.GO, CLAUSE, self.TEXT), (other, "R-1/2", "exit 4", how)))
                self.assertEqual((a.status, a.contracts), (V.ANCHORED, (self.GO.id,)))
        a = V.anchor(on_other, project((self.GO, CLAUSE, self.TEXT), (other, "R-1/2", "exit 4")))
        self.assertEqual((a.status, a.contracts), (V.CONTRADICTS_APPROVED, (other.id,)))

    def test_an_obligation_the_project_cannot_resolve_is_no_contract(self):
        for how in (NO_SPEC, NO_CONTRACT):
            with self.subTest(how=how):
                a = V.anchor(self.AGAIN, project((self.GO, CLAUSE, self.TEXT, how)))
                self.assertEqual((a.status, a.contracts), (V.UNANCHORED, ()))
                second = contract("BC-GO2", CLI, {"argv": ["go", "twice"]}, {"exit_code": 3})
                a = V.anchor(self.AGAIN, project((self.GO, CLAUSE, self.TEXT, how), (second, CLAUSE, self.TEXT)))
                self.assertEqual((a.status, a.contracts), (V.ANCHORED, (second.id,)))


class OutcomesStayDistinct(unittest.TestCase):
    """Pins aisef2/app/review_verify.py::_canon [5, 6]. The canonical text of an outcome or a stimulus keeps what
    differs distinct — [1, 2] is not [12] — so two approved contracts of a clause that expect different values are
    UNANCHORED, and two stimuli are two; and the outcome the reason hands the developer is that canonical text: JSON
    that parses to the clause's approved outcome."""

    def test_clause_outcomes_that_differ_are_not_one_constant(self):
        pair = contract("BC-A", FN, {"args": [1]}, {"returns": [1, 2]})
        twelve = contract("BC-B", FN, {"args": [2]}, {"returns": [12]})
        a = V.anchor(finding({"args": [3]}, {"returns": [1, 2]}, FN),
                     project((pair, CLAUSE, "returns the pair"), (twelve, CLAUSE, "returns the twelve")))
        self.assertEqual((a.status, a.contracts), (V.UNANCHORED, (pair.id, twelve.id)))

    def test_stimuli_that_differ_are_two_stimuli(self):
        one_two = contract("BC-P", FN, {"args": [1, 2]}, {"returns": 7})
        twelve = contract("BC-Q", FN, {"args": [12]}, {"returns": 7})
        a = V.anchor(finding({"args": [3]}, {"returns": 7}, FN),
                     project((one_two, CLAUSE, "returns the total"), (twelve, CLAUSE, "returns the total")))
        self.assertEqual((a.status, a.contracts), (V.ANCHORED, (one_two.id, twelve.id)))

    def test_the_approved_outcome_in_a_reason_is_json(self):
        outcome = {"exit_code": 3, "stdout": "ok"}
        a1 = contract("BC-A", CLI, {"argv": ["a"]}, outcome)
        a2 = contract("BC-B", CLI, {"argv": ["b"]}, outcome)
        rows = ((a1, CLAUSE, "the text"), (a2, CLAUSE, "the text"))
        other = {"exit_code": 4, "stdout": "ok"}
        for what, f, status, contracts in (
                ("anchored", finding({"argv": ["c"]}, outcome), V.ANCHORED, (a1.id, a2.id)),
                ("the clause's constant is otherwise", finding({"argv": ["c"]}, other), V.CONTRADICTS_APPROVED,
                 (a1.id, a2.id)),
                ("the stimulus is decided otherwise", finding({"argv": ["a"]}, other), V.CONTRADICTS_APPROVED,
                 (a1.id,))):
            with self.subTest(what):
                a = V.anchor(f, project(*rows))
                self.assertEqual((a.status, a.contracts), (status, contracts))
                body = a.reason[a.reason.index("{"): a.reason.rindex("}") + 1]
                try:
                    embedded = json.loads(body)
                except ValueError:
                    self.fail(f"the approved outcome in the reason is not JSON: {a.reason!r}")
                self.assertEqual(embedded, outcome)


class OutcomesHoldingLists(unittest.TestCase):
    """Pins aisef2/app/review_verify.py::_scalars [4, 5]. An outcome holding a list is read value by value like any
    other: with one approved contract, `returns [1, 2]` is stated by a text holding 1 and 2 and not by a text without
    them; a list of booleans is unstatable; `anchor` never raises on it."""

    def anchored(self, shape, outcome: dict, text: str) -> str:
        one = contract("BC-L", shape, {"args": [1]}, outcome)
        a = V.anchor(finding({"args": [2]}, outcome, shape), project((one, CLAUSE, text)))
        self.assertEqual(a.contracts, (one.id,))
        return a.status

    def test_a_list_is_stated_by_its_values(self):
        self.assertEqual(self.anchored(FN, {"returns": [1, 2]}, "returns 1 and 2"), V.ANCHORED)
        self.assertEqual(self.anchored(FN, {"returns": [1, 2]}, "returns the pair"), V.UNANCHORED)
        self.assertEqual(self.anchored(FN, {"returns": [1, 2]}, "returns 1, 2 and 3"), V.UNANCHORED)

    def test_a_list_inside_a_mapping_is_stated_by_its_values(self):
        nested = {"returns": {"items": [1, 2], "total": 3}}
        self.assertEqual(self.anchored(FN, nested, "returns items 1 and 2 with the total 3"), V.ANCHORED)
        self.assertEqual(self.anchored(FN, nested, "returns the items and their total"), V.UNANCHORED)
        files = {"files": {"out.txt": {"lines": [4, 5]}}}
        self.assertEqual(self.anchored(FILE, files, "out.txt holds the lines 4 and 5"), V.ANCHORED)
        self.assertEqual(self.anchored(FILE, files, "out.txt holds the lines"), V.UNANCHORED)

    def test_a_list_of_booleans_is_unstatable(self):
        self.assertEqual(self.anchored(FN, {"returns": [True, False]}, "returns true then false"), V.UNANCHORED)

    def test_a_list_of_lists_and_a_list_of_mappings_are_read_value_by_value(self):
        for what, outcome, stated, unstated in (
                ("lists of lists", {"returns": [[1, 2], [3]]}, "returns 1, 2 and 3 in two groups", "returns the groups"),
                ("a list of mappings", {"returns": [{"id": 1}, {"id": 2}]}, "returns the ids 1 and 2", "returns the ids")):
            with self.subTest(what):
                self.assertEqual(self.anchored(FN, outcome, stated), V.ANCHORED)
                self.assertEqual(self.anchored(FN, outcome, unstated), V.UNANCHORED)


class OutcomesNoTextCanState(unittest.TestCase):
    """Pins aisef2/app/review_verify.py::_states [2, 6, 8]. One approved contract anchors a clause's outcome by its
    text only when the text states every expected value; an outcome holding a boolean, a null or no scalar at all (an
    empty list or mapping) cannot be stated, so a finding expecting it on a new stimulus is UNANCHORED whatever digits
    the text holds, and does not block; a second approved contract giving the same outcome on a distinct stimulus
    shows the constant, no text needed."""

    UNSTATABLE = (("a null", {"returns": None}, "returns nothing"),
                  ("an empty list", {"returns": []}, "returns an empty list"),
                  ("an empty mapping", {"returns": {}}, "returns an empty mapping"),
                  ("a boolean, no digit in the text", {"raises": True}, "must raise an error"),
                  ("a boolean, its number in the text", {"raises": True}, "step 1: must raise an error"),
                  ("false, its number in the text", {"raises": False}, "step 0: must not raise"),
                  ("a boolean among numbers, the number in the text", {"returns": {"ok": True, "count": 1}},
                   "returns ok with count 1"),
                  ("a null among numbers, the number in the text", {"returns": {"next": None, "count": 2}},
                   "returns no next with count 2"))

    def test_an_outcome_a_clause_text_cannot_state_is_not_anchored_by_the_text(self):
        for what, outcome, text in self.UNSTATABLE:
            with self.subTest(what):
                f = finding({"args": [2]}, outcome, FN)
                a = V.anchor(f, project((contract("BC-U", FN, {"args": [1]}, outcome), CLAUSE, text)))
                self.assertEqual(a.status, V.UNANCHORED, a)
                self.assertFalse(V.blocks(CONFIRMED, f, "fix-loop", "low", a))

    def test_the_same_outcome_on_two_distinct_stimuli_is_anchored_without_the_text(self):
        for what, outcome, text in self.UNSTATABLE:
            with self.subTest(what):
                f = finding({"args": [2]}, outcome, FN)
                a = V.anchor(f, project((contract("BC-U1", FN, {"args": [1]}, outcome), CLAUSE, text),
                                        (contract("BC-U2", FN, {"args": [3]}, outcome), CLAUSE, text)))
                self.assertEqual((a.status, a.contracts), (V.ANCHORED, ("BC-U1", "BC-U2")))
                self.assertTrue(V.blocks(CONFIRMED, f, "fix-loop", "low", a))

    def test_a_number_the_text_states_anchors_by_the_text(self):
        f = finding({"args": [2]}, {"returns": 5}, FN)
        a = V.anchor(f, project((contract("BC-N", FN, {"args": [1]}, {"returns": 5}), CLAUSE, "returns 5")))
        self.assertEqual(a.status, V.ANCHORED)


class FloatAndStringOutcomes(unittest.TestCase):
    """Pins aisef2/app/review_verify.py::_states [10, 11]. A float outcome is stated iff the clause text holds that
    number and no other; a string outcome iff the text holds the string literally and no other number."""

    def status(self, outcome: dict, text: str) -> str:
        f = finding({"args": [2]}, outcome, FN)
        return V.anchor(f, project((contract("BC-V", FN, {"args": [1]}, outcome), CLAUSE, text))).status

    def test_a_float_is_stated_by_its_number_only(self):
        for text, status in (("returns 2.5 for the sample", V.ANCHORED), ("returns the mean", V.UNANCHORED),
                             ("returns 2.5 or 3", V.UNANCHORED)):
            with self.subTest(text):
                self.assertEqual(self.status({"returns": 2.5}, text), status)

    def test_a_string_is_stated_by_its_text_only(self):
        for text, status in (("returns the string ok", V.ANCHORED), ("returns a greeting", V.UNANCHORED),
                             ("returns the string ok in 3 cases", V.UNANCHORED)):
            with self.subTest(text):
                self.assertEqual(self.status({"returns": "ok"}, text), status)


class DefaultSpellings(unittest.TestCase):
    """Pins aisef2/app/review_verify.py::_stimulus [4, 5, 6, 7]. A stimulus is its non-default keys: a reproducer
    that spells stdin null, workspace {}, pre [] (for a python_callable also args [], args '', kwargs {}) is the same
    stimulus as an approved contract's that omits them — an approved contract that decides it otherwise makes the
    finding CONTRADICTS_APPROVED (a false finding, it does not block); and two approved contracts of one clause that
    differ only in such spellings are one stimulus, which does not by itself show a constant outcome."""

    #: (what, subject, the approved contract's stimulus, another stimulus, the key the finding spells, its default)
    CASES = (("stdin null", CLI, {"argv": ["missing"]}, {"argv": ["ok"]}, "stdin", None),
             ("workspace {}", CLI, {"argv": ["missing"]}, {"argv": ["ok"]}, "workspace", {}),
             ("pre []", CLI, {"argv": ["missing"]}, {"argv": ["ok"]}, "pre", []),
             ("args ''", FN, {}, {"args": [1]}, "args", ""),
             ("args []", FN, {}, {"args": [1]}, "args", []),
             ("kwargs {}", FN, {}, {"args": [1]}, "kwargs", {}))
    #: a stimulus of each kind that neither contract of a case has (the finding's own, in the second test)
    UNSEEN = {CLI: {"argv": ["unseen"]}, FN: {"args": [9]}}

    def test_a_default_spelling_is_the_stimulus_an_approved_contract_decides(self):
        """R-1/0 says exit/return 0 on success, R-1/3 says 3 for the stimulus `missing`: a finding that `missing` must
        give 0 (citing R-1/0, which the clause's own text and contract state) is a false finding, however the
        reviewer spells the stimulus."""
        for what, shape, decided, success, key, default in self.CASES:
            key_of = "exit_code" if shape is CLI else "returns"
            with self.subTest(what):
                ok = contract("BC-OK", shape, success, {key_of: 0})
                missing = contract("BC-MISSING", shape, decided, {key_of: 3})
                rows = ((ok, "R-1/0", "0 on success"), (missing, "R-1/3", "3 on an I/O error"))
                for spelled in (decided, {**decided, key: default}):     # the control, then the spelling
                    f = finding(spelled, {key_of: 0}, shape, clause="R-1/0")
                    a = V.anchor(f, project(*rows))
                    self.assertEqual((a.status, a.contracts), (V.CONTRADICTS_APPROVED, (missing.id,)), spelled)
                    self.assertFalse(V.blocks(CONFIRMED, f, "fix-loop", "low", a))

    def test_spellings_of_one_stimulus_do_not_show_a_constant_outcome(self):
        for what, shape, plain_stimulus, other, key, default in self.CASES:
            key_of = "exit_code" if shape is CLI else "returns"
            with self.subTest(what):
                p = contract("BC-P", shape, plain_stimulus, {key_of: 3})
                spelled = contract("BC-Q", shape, {**plain_stimulus, key: default}, {key_of: 3})
                distinct = contract("BC-Q", shape, other, {key_of: 3})
                text = "the I/O failure code"        # states no value: only distinct stimuli show the constant
                f = finding(self.UNSEEN[shape], {key_of: 3}, shape)
                a = V.anchor(f, project((p, CLAUSE, text), (spelled, CLAUSE, text)))
                self.assertEqual((a.status, a.contracts), (V.UNANCHORED, ("BC-P", "BC-Q")))
                a = V.anchor(f, project((p, CLAUSE, text), (distinct, CLAUSE, text)))     # the control
                self.assertEqual((a.status, a.contracts), (V.ANCHORED, ("BC-P", "BC-Q")))


REFERENCE = ROOT / "tests/v2/fixtures/workloads/ledgerlock-reference/reference/ledgerlock"
PROBE = "probe.cli_invocation"
MAIN = {"kind": "cli_invocation", "locator": "ledgerlock:__main__"}
SNAPSHOT_MISSING = {"clause": "R-9/3", "subject": MAIN, "stimulus": {"argv": ["snapshot", "<ws>/missing.jsonl"]},
                    "observable": {"exit_code": 3, "within_s": 20}}
#: the reference with one change: `snapshot` of a missing file no longer fails (the defect of smoke #2's R-9/3 finding)
MISSING_OK = ("ledger.py", "        records, _ = self._records(missing_ok=False)",
              "        records, _ = self._records(missing_ok=True)")


class VerifyBase(unittest.TestCase):
    """The fixtures of the `verify` classes: a scratch directory, a copy of the LedgerLock reference."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name)

    def checkout(self, change=None) -> pathlib.Path:
        root = self.tmp / "checkout"
        shutil.copytree(REFERENCE, root / "ledgerlock", ignore=shutil.ignore_patterns("__pycache__"))
        if change:
            name, old, new = change
            p = root / "ledgerlock" / name
            text = p.read_text(encoding="utf-8")
            self.assertEqual(text.count(old), 1, f"the defect's shape no longer matches the reference: {old!r}")
            p.write_text(text.replace(old, new), encoding="utf-8")
        return root

    def verify(self, reproducer: dict, root: pathlib.Path | None = None, interpreter: str | None = None):
        return V.verify({"id": "F-1", "severity": "high", "reproducer": reproducer}, requirements={"R-9": object()},
                        product_roots=("ledgerlock",), root=str(root or self.tmp), revision="0" * 40, timeout_s=60,
                        interpreter=interpreter or sys.executable)

    def untriaged(self, v, *, probe: str | None) -> None:
        """What every path that cannot verify answers: a Verification that is UNVERIFIABLE — never evidence, never
        blocking — and says which probe (if any) was in play."""
        self.assertIsInstance(v, V.Verification)
        self.assertEqual((v.status, v.probe, v.observed), (V.UNVERIFIABLE, probe, None))
        self.assertEqual(v.evidence(), "")
        self.assertFalse(V.blocks(v, {"id": "F-1", "severity": "critical"}, "fix-loop", "low",
                                  V.Anchor(V.ANCHORED, "anchored")))


class CannotVerifyIsTriage(VerifyBase):
    """Pins aisef2/app/review_verify.py::verify [9, 13, 15, 21, 22]. `verify` only ever answers a Verification: a
    reproducer on a subject kind no active probe observes, an observation the probe gives no meaning, one no
    calibration qualifies at the bytes that run, or a probe that cannot run is UNVERIFIABLE — triage, not a crash of
    the review stage — and the reason names the identifying element (the kind, the probe, the class, the missing
    interpreter or checkout) and the class of its cause (no probe, refused, not calibrated, did not execute)."""

    def test_a_subject_kind_no_active_probe_observes(self):
        rep = {**SNAPSHOT_MISSING, "subject": {"kind": "http_route", "locator": "ledgerlock:__main__"},
               "stimulus": {"path": "/"}, "observable": {"status": 200, "within_s": 5}}
        with mock.patch.object(V, "run_probe", side_effect=AssertionError("nothing observes http_route")):
            v = self.verify(rep)
        self.untriaged(v, probe=None)
        self.assertIn("http_route", v.reason)
        self.assertIn("probe", v.reason)          # the cause class: no probe observes it

    def test_an_observation_the_probe_gives_no_meaning_is_refused(self):
        for what, observable in (("no window", {"exit_code": 3}), ("an observable of no class", {"vibes": "bad", "within_s": 5})):
            with self.subTest(what):
                v = self.verify({**SNAPSHOT_MISSING, "observable": observable})
                self.untriaged(v, probe=PROBE)
                self.assertIn(PROBE, v.reason)
                self.assertIn("refused", v.reason)    # the cause class: the probe refused, it did not degrade

    def test_an_observation_no_calibration_qualifies_at_the_bytes_that_run_is_not_executed(self):
        for what, patch in (("the probe's bytes are not the calibrated ones",
                             mock.patch.object(V, "executing", lambda probe: "0" * 64)),
                            ("the release ships no calibrations", mock.patch("aisef2.app.run.calibrations",
                                                                              return_value=()))):
            with self.subTest(what), patch, \
                    mock.patch.object(V, "run_probe", side_effect=AssertionError("an unqualified observation ran")):
                v = self.verify(SNAPSHOT_MISSING)
                self.untriaged(v, probe=PROBE)
                self.assertIn(PROBE, v.reason)
                self.assertIn("exits", v.reason)      # the observation class that is not calibrated
                self.assertIn("calibrated", v.reason)

    def test_a_probe_that_cannot_run_is_unverifiable_with_its_own_detail(self):
        v = self.verify(SNAPSHOT_MISSING, interpreter=str(pathlib.Path(self.tmp.anchor, "no-such-interpreter")))
        self.untriaged(v, probe=PROBE)       # (at the filesystem's root: the reason is bounded, a long path would cut)
        self.assertIn("interpreter", v.reason)
        self.assertIn("no-such-interpreter", v.reason)
        v = self.verify(SNAPSHOT_MISSING, root=self.tmp / "gone-checkout")
        self.untriaged(v, probe=PROBE)
        self.assertIn("checkout", v.reason)
        self.assertIn("missing", v.reason)


class ConfirmedFindingNamesItsIdentifiers(VerifyBase):
    """Pins aisef2/app/review_verify.py::verify [27]. A CONFIRMED finding's reason — the `why` of the gate row the
    developer's retry prompt prints next to the probe's evidence — carries the probe's id and the requirement's id each
    as an identifier of its own (not run into its neighbour: `probe.cli_invocationR-9` names nothing), so that each can
    be found by a reader or a search of the journal. Punctuation around an id is not asserted."""

    @staticmethod
    def names(reason: str, ident: str) -> bool:
        return re.search(r"(?<![\w.-])" + re.escape(ident) + r"(?![\w.-])", reason) is not None

    def test_the_probe_and_the_requirement_are_identifiers_of_their_own_in_the_reason(self):
        v = self.verify(SNAPSHOT_MISSING, self.checkout(MISSING_OK))
        self.assertEqual((v.status, v.probe, v.observed), (V.CONFIRMED, PROBE, "REFUTED"))
        self.assertTrue(self.names(v.reason, PROBE), v.reason)
        self.assertTrue(self.names(v.reason, "R-9"), v.reason)
        self.assertFalse(self.names("probe.cli_invocationR-9 is said to demand", PROBE))      # the checker itself
        self.assertTrue(self.names("probe.cli_invocation: R-9, is said", PROBE))


if __name__ == "__main__":
    unittest.main()
