"""V2.1 mutation survivors, batch T15a: the review verifier's anchor, statement and reproducer contract
(aisef2/app/review_verify.py: `anchor`, `detail`, `reproducer_contract`).

Each class states the requirement a group of survivors guards and who relies on it:

* anchor — a finding whose reproducer is an object always gets an Anchor. Reviewer.review journals `anchor` and
  `anchor_why` only for a non-None Anchor, and `blocks()` treats None like UNANCHORED, so an anchor() that answered
  None would drop the only record of why a CONFIRMED finding did not block; a finding the clause's approved
  contracts cannot anchor is refused with a status, never an exception (an exception reaches app/run.py and the story
  is REFUSED); the contracts an anchor rests on are named in its reason as separate identifiers.
* detail — the journaled statement of a finding (the gate row the developer's retry prompt is printed from) is
  data: the finding, the normalised severity, the summary, the clause, the verification and its reason, the anchor
  and its reason, and the reproducer, each under its own key; the reviewer's characters are kept.
* reproducer_contract — a reproducer that is not a contract is a *reason* (verify -> UNVERIFIABLE, anchor ->
  UNANCHORED), never an exception and never None; the subject is exactly an object of kind and locator in any key
  order; the contract a reproducer becomes states what the requirement demands (MUST_HOLD) and requires its subject,
  so a finding about a module the candidate lacks is never CONFIRMED; a `path:` locator is judged by its path; the
  finding's own id never decides whether its reproducer is verified.

The fixtures are those of tests/v2/test_v21_review.py (the 2.0.0 LedgerLock bundle, its reference checkout)."""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import review_verify as V  # noqa: E402
from aisef2.app.bundle_cli import _mint  # noqa: E402
from aisef2.arch.enums import BehaviorVerdict, Polarity, SubjectAbsence, SubjectKind  # noqa: E402
from aisef2.probe import catalog  # noqa: E402
from aisef2.product.compiler import ProbeRef  # noqa: E402
from aisef2.product.contract import BehaviorContract  # noqa: E402
from tests.v2 import test_v21_review as base  # noqa: E402

PROJECT = base.LEDGERLOCK
MAIN = base.MAIN
SNAPSHOT_MISSING = ["snapshot", "<ws>/missing.jsonl"]
#: R-9/3 (exit 3 on an I/O error) is approved on two stimuli (BC-V22-S-9-d, -e); R-3.1/2 on a process effect by two
#: contracts that observe different keys (-b `raises`, -c `files`); R-3.3/2 expects 3 lines in one and 5 in another
PROCESS = {"kind": "process_effect", "locator": "ledgerlock.ledger:Ledger"}
CONSTRUCT = {"scenario": [{"step": "construct", "args": ["<ws>/l.jsonl"], "kwargs": {}}]}
PROBE_RUNS = unittest.skipUnless(os.name == "posix" or sys.platform == "win32", "the probe runs on both")


def finding(clause: str = "R-9/3", **reproducer) -> dict:
    """A model reviewer's finding: `snapshot` of a missing file must exit 3 (R-9/3); `reproducer` overrides its keys."""
    rep = {**base.reproducer(clause, SNAPSHOT_MISSING, 3), **reproducer}
    return {"id": "FND-1", "severity": "high", "summary": "snapshot of a missing file must exit 3", "reproducer": rep}


def contract_of(f: dict):
    return V.reproducer_contract(f, PROJECT.requirements, PROJECT.product_roots)


class Checkout(unittest.TestCase):
    """A scratch directory per test and the LedgerLock reference copied into it (a probe runs on a real checkout)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)

    def checkout(self, name: str = "reference", *, without: tuple[str, ...] = ()) -> pathlib.Path:
        """The reference copied under `name`, less the module files named by `without` (a candidate that lacks them)."""
        root = self.tmp / name
        shutil.copytree(base.REFERENCE, root / "ledgerlock",
                        ignore=shutil.ignore_patterns("__pycache__", *without))
        return root

    def verify(self, f: dict, root: pathlib.Path) -> V.Verification:
        return V.verify(f, requirements=PROJECT.requirements, product_roots=PROJECT.product_roots,
                        root=os.fspath(root), revision="0" * 40, timeout_s=60, interpreter=sys.executable)


# ------------------------------------------------------------------------------------------------------- anchor

class AnchorAnswersEveryRefusal(unittest.TestCase):
    """anchor() returns an Anchor, UNANCHORED and naming the cause, for every finding whose reproducer is an object
    and which cannot be anchored: the finding's row in the journal is the only record of why a CONFIRMED finding did
    not block (Reviewer.review journals `anchor`/`anchor_why` only for a non-None Anchor).

    Pins aisef2/app/review_verify.py::anchor [8, 14] and, through the abbreviated subject kind, reproducer_contract
    [27, 29] (an exception or a None out of reproducer_contract fails here first)"""

    def anchor(self, f: dict) -> V.Anchor:
        a = V.anchor(f, PROJECT)
        self.assertIsInstance(a, V.Anchor, "anchor() answered nothing: the finding would carry no anchor row")
        return a

    def test_a_reproducer_that_is_not_a_contract_is_unanchored_and_says_why(self):
        for what, change, element in (
                ("an abbreviated subject kind", {"subject": {"kind": "cli", "locator": MAIN["locator"]}}, "cli"),
                ("a clause of no requirement", {"clause": "R-404/1"}, "R-404/1"),
                ("a subject outside the product", {"subject": {"kind": MAIN["kind"], "locator": "elsewhere:__main__"}},
                 "elsewhere"),
                ("a stimulus that is not an object", {"stimulus": "snapshot"}, "stimulus")):
            with self.subTest(what):
                a = self.anchor(finding(**change))
                self.assertEqual(a.status, V.UNANCHORED)
                self.assertIn(element, a.reason)

    def test_a_clause_no_approved_contract_declares_is_unanchored_and_names_the_clause(self):
        """R-9 and R-7 are requirements of the bundle; none of their approved contracts declares clauses 9/9, 7/9:
        the commonest false finding (a clause the plan has no criterion for)."""
        for clause in ("R-9/9", "R-7/9"):
            with self.subTest(clause):
                a = self.anchor(finding(clause))
                self.assertEqual(a.status, V.UNANCHORED)
                self.assertIn(clause, a.reason)


class AnchorKeysTheClauseDoesNotObserve(unittest.TestCase):
    """A finding that states keys the clause's approved contracts (on that subject) do not all observe, or states
    none, is UNANCHORED and the reason names the clause and the keys — never an exception out of anchor() (the story
    would be REFUSED for one reviewer finding) and never ANCHORED against an outcome of nothing.

    Pins aisef2/app/review_verify.py::anchor [17, 18]"""

    def test_a_key_the_approved_contracts_do_not_observe_is_unanchored_naming_clause_and_key(self):
        for clause, subject, stimulus, observable, key in (
                # no approved contract of R-9/3 observes the streams
                ("R-9/3", MAIN, base.reproducer("R-9/3", SNAPSHOT_MISSING, 3)["stimulus"],
                 {"stdout": "boom", "within_s": 20}, "stdout"),
                # BC-V22-S-3.1-b observes `raises`, BC-V22-S-3.1-c only `files`: one of them lacks the key
                ("R-3.1/2", PROCESS, CONSTRUCT, {"raises": True, "within_s": 20}, "raises")):
            with self.subTest(clause, key=key):
                f = finding(clause, subject=subject, stimulus=stimulus, observable=observable)
                a = V.anchor(f, PROJECT)
                self.assertIsInstance(a, V.Anchor)
                self.assertEqual(a.status, V.UNANCHORED)
                self.assertIn(clause, a.reason)
                self.assertIn(key, a.reason)

    def test_a_finding_that_states_no_outcome_is_not_anchored(self):
        """The observable holds only the window: there is no outcome to be the clause's approved one."""
        a = V.anchor(finding(observable={"within_s": 5}), PROJECT)
        self.assertIsInstance(a, V.Anchor)
        self.assertEqual(a.status, V.UNANCHORED)
        self.assertIn("R-9/3", a.reason)


class AnchorOutcomeThatDependsOnTheStimulus(unittest.TestCase):
    """A clause whose approved contracts expect different values for different stimuli (R-3.3/2: 3 lines in one,
    5 in another) anchors no new stimulus: UNANCHORED, the approved contracts named in `contracts` and the clause in
    the reason — so the journal says which approved contracts disagree.

    Pins aisef2/app/review_verify.py::anchor [21]"""

    APPROVED = ("BC-V22-S-3.3-d", "BC-V22-S-D3-05-01-1")

    def test_the_contracts_that_disagree_are_named(self):
        counts = sorted(V.plain(PROJECT.contracts[c].observable)["files"]["<ws>/l.jsonl"]["line_count"]
                        for c in self.APPROVED)
        self.assertEqual(counts, [3, 5])      # the premise: the clause's approved outcomes differ
        f = finding("R-3.3/2", subject=PROCESS, stimulus=CONSTRUCT,
                    observable={"files": {"<ws>/l.jsonl": {"line_count": 4}}, "within_s": 30})
        a = V.anchor(f, PROJECT)
        self.assertIsInstance(a, V.Anchor)
        self.assertEqual((a.status, a.contracts), (V.UNANCHORED, self.APPROVED))
        self.assertIn("R-3.3/2", a.reason)


class AnchoredReasonNamesItsContracts(unittest.TestCase):
    """An ANCHORED finding's reason is what the gate row (`anchor_why`) and the developer's retry prompt tell about
    the approved contracts the block rests on: each id of `Anchor.contracts` occurs in it as a separate identifier
    (not fused with its neighbour), with the clause and the approved outcome.

    Pins aisef2/app/review_verify.py::anchor [80]; its R-12/1 case anchors on `path:ledgerlock`, so it also pins
    reproducer_contract [57]"""

    def test_each_contract_id_is_a_separate_identifier_in_the_reason(self):
        no_popen = {"clause": "R-12/1", "subject": {"kind": "file_artifact", "locator": "path:ledgerlock"},
                    "stimulus": {"grep": r"\bos\.popen\b", "suffixes": [".py"]},
                    "observable": {"matches": 0, "within_s": 30}}
        for clause, f, ids, outcome in (
                ("R-9/3", finding(), ("BC-V22-S-9-d", "BC-V22-S-9-e"), {"exit_code": 3}),
                ("R-12/1", {"id": "FND-2", "severity": "high", "summary": "no process is started",
                            "reproducer": no_popen},
                 ("BC-V22-S-12-a", "BC-V22-S-12-b", "BC-V22-S-12-c"), {"matches": 0})):
            with self.subTest(clause):
                a = V.anchor(f, PROJECT)
                self.assertEqual((a.status, a.contracts), (V.ANCHORED, ids))
                for cid in ids:
                    self.assertRegex(a.reason, r"(?<![\w.-])" + re.escape(cid) + r"(?![\w.-])")
                self.assertIn(clause, a.reason)
                stated = re.search(r"\{.*\}", a.reason)
                self.assertIsNotNone(stated, a.reason)
                self.assertEqual(json.loads(stated.group(0)), outcome)


# -------------------------------------------------------------------------------------------------------- detail

class StatementOfAFinding(unittest.TestCase):
    """detail() is the journaled statement the developer's retry prompt is printed from and the audit record of the
    decision's inputs: every field is data under its own key, equal to what was stated — the finding's id, the
    severity as normalised for the floor, the reviewer's summary, the cited clause, the verification and its reason,
    the anchor and its reason (only when there is one) and the reproducer's subject, stimulus and observable. The
    reviewer's characters are kept (a non-ASCII summary is not journaled as \\uXXXX escapes).

    Pins aisef2/app/review_verify.py::detail [3, 4, 5, 6, 8, 12, 13, 14, 15, 17, 18, 21, 23, 28, 29, 30, 32, 33, 35]"""

    SUMMARY = "tệp thiếu → snapshot of a missing file must exit 3"

    def test_a_confirmed_and_anchored_finding_is_stated_in_full(self):
        f = finding()
        f.update(id="FND-7", severity="HIGH", summary=self.SUMMARY)
        v = V.Verification(V.CONFIRMED, "probe.cli_invocation refutes the behaviour R-9 is said to demand",
                           "probe.cli_invocation", "REFUTED")
        a = V.anchor(f, PROJECT)
        self.assertEqual(a.status, V.ANCHORED)
        text = V.detail(f, v, a)
        rep = f["reproducer"]
        self.assertEqual(json.loads(text), {
            "finding": "FND-7", "severity": "high", "summary": self.SUMMARY, "clause": "R-9/3",
            "verification": V.CONFIRMED, "why": v.reason, "observed": v.observed, "anchor": V.ANCHORED,
            "anchor_why": a.reason,
            "reproducer": {"subject": MAIN, "stimulus": rep["stimulus"], "observable": rep["observable"]}})
        self.assertIn("tệp", text)
        self.assertNotIn("\\u", text)

    def test_a_finding_without_a_reproducer_states_no_clause_no_reproducer_and_no_anchor(self):
        f = {"id": "FND-8", "severity": "CRITICAL", "summary": "looks wrong"}
        v = V.Verification(V.UNVERIFIABLE, "no reproducer: the finding states no observable behaviour")
        self.assertEqual(json.loads(V.detail(f, v)), {
            "finding": "FND-8", "severity": "critical", "summary": "looks wrong", "clause": None,
            "verification": V.UNVERIFIABLE, "why": v.reason, "reproducer": None})

    def test_an_unknown_severity_is_stated_as_low_and_a_malformed_reproducer_is_echoed_as_written(self):
        f = finding(subject={"kind": "cli", "locator": MAIN["locator"]})
        f.update(id="FND-9", severity="SEVERE")
        a = V.anchor(f, PROJECT)
        self.assertEqual(a.status, V.UNANCHORED)
        v = V.Verification(V.UNVERIFIABLE, a.reason)
        stated = json.loads(V.detail(f, v, a))
        self.assertEqual((stated["finding"], stated["severity"], stated["clause"]), ("FND-9", "low", "R-9/3"))
        self.assertEqual((stated["anchor"], stated["anchor_why"]), (V.UNANCHORED, a.reason))
        self.assertEqual(stated["reproducer"]["subject"], {"kind": "cli", "locator": MAIN["locator"]})
        self.assertEqual(stated["reproducer"]["observable"], f["reproducer"]["observable"])


# ------------------------------------------------------------------------------------------ reproducer_contract

class SubjectIsExactlyKindAndLocator(Checkout):
    """A reproducer's subject is exactly an object of `kind` and `locator`: null, a string, a list, a number, an
    object missing either key, carrying an extra one or naming one of the two otherwise is refused as a reason that
    names both keys — by
    reproducer_contract, by verify (UNVERIFIABLE) and by anchor (UNANCHORED) — and never raises, so one malformed
    reproducer from a reviewer cannot fail the story.

    Pins aisef2/app/review_verify.py::reproducer_contract [12, 13, 25]"""

    SHAPES = (("null", None), ("a string", "cli_invocation"), ("a list of the two keys", ["kind", "locator"]),
              ("a number", 5), ("an empty object", {}), ("an object without locator", {"kind": MAIN["kind"]}),
              ("an object without kind", {"locator": MAIN["locator"]}), ("an object with an extra key", {**MAIN, "x": 1}),
              # two keys, so a count of keys is not the check: one of them is not `locator` (resp. `kind`)
              ("two keys, one misnamed (path)", {"kind": MAIN["kind"], "path": MAIN["locator"]}),
              ("two keys, one misnamed (type)", {"type": MAIN["kind"], "locator": MAIN["locator"]}))

    def test_every_other_shape_is_refused_with_a_reason_naming_both_keys(self):
        for what, subject in self.SHAPES:
            f = finding(subject=subject)
            with self.subTest(what):
                c = contract_of(f)
                self.assertIsInstance(c, str)
                v = self.verify(f, self.tmp)     # refused before the probe: the root is never read
                a = V.anchor(f, PROJECT)
                self.assertEqual((v.status, a.status), (V.UNVERIFIABLE, V.UNANCHORED))
                for reason in (c, v.reason, a.reason):
                    self.assertIn("kind", reason)
                    self.assertIn("locator", reason)

    def test_the_order_of_the_keys_is_not_part_of_the_subject(self):
        """JSON object key order carries no meaning and json.loads keeps the writer's: {locator, kind} is the same
        subject as {kind, locator}."""
        swapped = json.loads('{"locator": "%s", "kind": "%s"}' % (MAIN["locator"], MAIN["kind"]))
        c = contract_of(finding(subject=swapped))
        self.assertIsInstance(c, BehaviorContract)
        self.assertEqual((c.subject.kind, c.subject.locator), (SubjectKind.CLI_INVOCATION, MAIN["locator"]))
        self.assertEqual(c, contract_of(finding()))
        self.assertEqual(V.anchor(finding(subject=swapped), PROJECT).status, V.ANCHORED)


class ReproducerThatIsNotAContractIsAReason(Checkout):
    """What the contract layer refuses (an unknown subject kind — a reviewer's abbreviation —, a stimulus or an
    observable that is not an object, a number with no canonical form, a part that names a test file) is a reason that
    carries the offending element: verify -> UNVERIFIABLE, anchor -> UNANCHORED; never None (both callers would die on
    `c.subject`) and never an exception.

    Pins aisef2/app/review_verify.py::reproducer_contract [27, 29]"""

    CASES = (
        ("kind 'cli'", {"subject": {"kind": "cli", "locator": MAIN["locator"]}}, "'cli'"),
        ("kind 'python'", {"subject": {"kind": "python", "locator": MAIN["locator"]}}, "'python'"),
        ("kind 'file'", {"subject": {"kind": "file", "locator": MAIN["locator"]}}, "'file'"),
        ("a stimulus that is a string", {"stimulus": "argv"}, "stimulus"),
        ("an observable that is a list", {"observable": [3]}, "observable"),
        ("a number with no canonical form", {"observable": {"exit_code": float("nan"), "within_s": 20}}, "finite"),
        ("a part that names a test file", {"stimulus": {"argv": ["tests/test_x.py"]}}, "tests/test_x.py"),
    )

    def test_the_refusal_is_a_reason_with_the_cause(self):
        for what, change, element in self.CASES:
            f = finding(**change)
            with self.subTest(what):
                c = contract_of(f)
                self.assertIsInstance(c, str)
                v = self.verify(f, self.tmp)     # refused before the probe: the root is never read
                a = V.anchor(f, PROJECT)
                self.assertEqual((v.status, a.status), (V.UNVERIFIABLE, V.UNANCHORED))
                for reason in (c, v.reason, a.reason):
                    self.assertIn(element, reason)


class NoReproducerIsRefusedNamingIt(Checkout):
    """verify() and anchor() are the module's public entry points (verify is the named authority of
    validation/qualification/authority_limits.py): a finding with no reproducer object — absent, null, a string — is
    refused as a reason that names the reproducer that is missing, which is what a caller journals as `why`. The
    product's own path answers such a finding before it gets here (Reviewer._verify, tested in
    tests/v2/test_v21_kills_adapters.py), so this pins the module's contract for a direct caller.

    Pins aisef2/app/review_verify.py::reproducer_contract [18]"""

    def test_the_reason_names_the_missing_reproducer(self):
        for what, extra in (("absent", {}), ("null", {"reproducer": None}), ("a string", {"reproducer": "run it"})):
            f = {"id": "F1", "severity": "high", "summary": "looks wrong", **extra}
            with self.subTest(what):
                c = contract_of(f)
                self.assertIsInstance(c, str)
                v = self.verify(f, self.tmp)
                a = V.anchor(f, PROJECT)
                self.assertEqual((v.status, a.status), (V.UNVERIFIABLE, V.UNANCHORED))
                for reason in (c, v.reason, a.reason):
                    self.assertIn("reproducer", reason)


class ReproducerContractStatesTheRequirement(unittest.TestCase):
    """The contract a reproducer becomes states what the requirement demands (MUST_HOLD: the spec's candidate
    expectation is SATISFIED) and REQUIRES its subject: for a subject the candidate does not contain the probe
    reports SUBJECT_ABSENT/REFUTED, which REQUIRES_SUBJECT drops (INDETERMINATE: undecided, status INDETERMINATE) — so a finding
    about a module a later story introduces is never CONFIRMED and never blocks, however well it anchors.

    Pins aisef2/app/review_verify.py::reproducer_contract [45, 46]"""

    def test_the_minted_spec_expects_the_behaviour_and_requires_the_subject(self):
        c = contract_of(finding())
        self.assertIsInstance(c, BehaviorContract)
        self.assertIs(c.polarity, Polarity.MUST_HOLD)
        self.assertIs(c.subject_absence, SubjectAbsence.REQUIRES_SUBJECT)
        e = catalog.active()[SubjectKind.CLI_INVOCATION]
        spec = _mint(c, ProbeRef(e.probe_id, e.probe_digest))
        self.assertIs(spec.candidate_expectation, BehaviorVerdict.SATISFIED)
        self.assertEqual(spec.probe_input["subject_absence"], SubjectAbsence.REQUIRES_SUBJECT.value)


@PROBE_RUNS
class AFindingAboutAnAbsentSubject(Checkout):
    """The candidate has no `ledgerlock/__main__.py`; the finding is anchored (R-9/3, exit 3) and critical. The probe
    runs and reports the subject absent: not CONFIRMED, status and observed INDETERMINATE, never blocks.

    Pins aisef2/app/review_verify.py::reproducer_contract [46]"""

    def test_it_is_not_confirmed_and_does_not_block(self):
        root = self.checkout(without=("__main__.py",))
        self.assertFalse((root / "ledgerlock" / "__main__.py").exists())
        f = finding()
        f["severity"] = "critical"
        v = self.verify(f, root)
        a = V.anchor(f, PROJECT)
        self.assertEqual(a.status, V.ANCHORED)
        self.assertEqual((v.status, v.observed), (V.INDETERMINATE, "INDETERMINATE"), v)     # not NOT_REPRODUCED (owner, 2026-10-15)
        self.assertIn("INDETERMINATE", v.reason, v)     # RV-2: the reason says the probe decided nothing ...
        self.assertNotIn("does not reproduce", v.reason, v)     # ... never that the finding was shown not to reproduce
        self.assertFalse(V.blocks(v, f, "fix-loop", "low", a))
        self.assertEqual(v.evidence(), "")


@PROBE_RUNS
class FindingIdDoesNotDecideVerification(Checkout):
    """The finding's own id never decides whether its reproducer is verified: an empty, a blank and an absent id give
    a contract (the id is model-written; the contract's id is derived from it with a prefix that is never empty),
    the finding anchors, and verify reaches the probe.

    Pins aisef2/app/review_verify.py::reproducer_contract [48]"""

    def test_an_empty_blank_or_absent_id_still_has_a_contract_an_anchor_and_a_verification(self):
        for what, fid in (("empty", ""), ("blank", "   "), ("absent", None)):
            f = finding()
            if fid is None:
                del f["id"]
            else:
                f["id"] = fid
            with self.subTest(what):
                self.assertIsInstance(contract_of(f), BehaviorContract)
                self.assertEqual(V.anchor(f, PROJECT).status, V.ANCHORED)

    def test_verify_reaches_the_probe_for_an_empty_id(self):
        f = finding()
        f["id"] = ""
        v = self.verify(f, self.checkout())
        self.assertEqual(v.status, V.NOT_REPRODUCED, v)      # the reference exits 3: the finding does not reproduce
        self.assertEqual(v.observed, "SATISFIED")


class PathLocatorIsJudgedByItsPath(unittest.TestCase):
    """A file_artifact locator `path:<p>` is in the product iff <p>'s top-level name is a product root: the prefix
    is not part of the name. A finding about `path:ledgerlock/ledger.py` verifies, `path:ledgerlock` anchors on
    R-12/1's approved contracts, and `path:other/x.py` is refused naming the locator — also when a product root is
    literally called `path`.

    Pins aisef2/app/review_verify.py::reproducer_contract [57]"""

    @staticmethod
    def artifact(locator: str) -> dict:
        return {"id": "FND-3", "severity": "high", "summary": "no process is started", "reproducer": {
            "clause": "R-12/1", "subject": {"kind": "file_artifact", "locator": locator},
            "stimulus": {"grep": r"\bos\.popen\b", "suffixes": [".py"]}, "observable": {"matches": 0, "within_s": 30}}}

    def test_a_path_inside_a_product_root_is_a_contract(self):
        for locator in ("path:ledgerlock", "path:ledgerlock/ledger.py"):
            with self.subTest(locator):
                c = V.reproducer_contract(self.artifact(locator), PROJECT.requirements, ("ledgerlock",))
                self.assertIsInstance(c, BehaviorContract)
                self.assertEqual((c.subject.kind, c.subject.locator), (SubjectKind.FILE_ARTIFACT, locator))

    def test_a_path_outside_every_product_root_is_refused_naming_the_locator(self):
        """`path:other/x.py` is no product root's; nor is a directory whose name only begins with a root's."""
        for locator in ("path:other/x.py", "path:ledgerlock_extra/x.py"):
            for roots in (("ledgerlock",), ("path",)):
                with self.subTest(locator, roots=roots):
                    c = V.reproducer_contract(self.artifact(locator), PROJECT.requirements, roots)
                    self.assertIsInstance(c, str)
                    self.assertIn(locator, c)

    def test_the_clause_anchors_the_finding_about_the_product_root(self):
        a = V.anchor(self.artifact("path:ledgerlock"), PROJECT)
        self.assertEqual(a.status, V.ANCHORED, a)
        self.assertEqual(len(a.contracts), 3)


if __name__ == "__main__":
    unittest.main()
