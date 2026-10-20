"""V2.1 (owner decision 2026-10-15, item 1) — an approval is not kept only because its contract's hash did not change:
`aisef bundle migrate` (and `seal --keep-approvals-from`) carry an approval over only while the contract it approved is
still evaluated as it was, derived from what each probe declares it changed (`CAPABILITY_CHANGES`), never from a
contract's name.

* the declarations: every probe of the catalog declares every capability version above 1, in a form the reader takes,
  and what file_artifact declares (PM-9, PM-11) is what the probe gives;
* a small bundle in the shape 2.0.0 wrote — one contract of each kind that is, and is not, selected — migrated: what is
  withheld and why, what is kept, the input never written, nothing approved by the tool, the command it prints works;
  each declared change selects by itself, by class and by `subject_absence`;
* the fail-closed side: a change nobody declared, a malformed record, a probe with no version, a probe that is not the
  release's, an approval that no longer binds — each withholds, and a release already at the current version withholds
  nothing;
* the real 2.0.0 LedgerLock bundle (closure-evidence, read only): exactly six of its 59 approvals are withheld — its
  six counts (grep_count, REQUIRES_SUBJECT): the four over the directory `ledgerlock` that the owner named and the two
  over one .py file each. A selector sees a contract's class and `subject_absence`, never its path or the repository, so
  PM-9 and PM-11 each select all six; what tells the four from the two is the `when` of each change, which the report
  prints beside the contract: PM-9's condition (a path that selects no file) can hold for a file only when a directory
  bears its name, PM-11's (a byte-order mark) holds for a file as for a directory. The candidate lints NOT_READY with
  those six to approve, and running the printed commands in a scratch copy makes it READY — under the shipped
  calibration rows re-bound to the bytes that run now (the shipped table is stale for every probe at this commit, so
  admission itself is the final snapshot's to show);
* what the keep rests on: `approvals_kept_grounds` (which versions were read) and `limits` (what a declaration-reading
  rule cannot see), the commands as the operator pastes them (the candidate's own path, the files they write, the
  placeholder approver refused), the candidate's two digests;
* `seal --keep-approvals-from` applies the same rule, and refuses approvals handed over without it.

Offline; no provider, no probe runs a subject (one test runs file_artifact over a plain directory)."""

from __future__ import annotations

import contextlib
import copy
import dataclasses
import hashlib
import io
import json
import pathlib
import re
import shlex
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle as B  # noqa: E402
from aisef2.app import bundle_cli  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.calibrations import CALIBRATIONS  # noqa: E402
from aisef2.arch.enums import (  # noqa: E402
    BehaviorVerdict, ObligationRole, Polarity, SubjectAbsence, SubjectKind,
)
from aisef2.plan.obligation import EXPECTED_AT_PARENT, NOT_PREREGISTERED, Plan, PlanObligation  # noqa: E402
from aisef2.probe import catalog  # noqa: E402
from aisef2.probe import file_artifact as fa  # noqa: E402
from aisef2.probe.calibration import executing  # noqa: E402
from aisef2.probe.protocol import RevisionRef, run_probe  # noqa: E402
from aisef2.product.approval import ContractApproval, Requirement  # noqa: E402
from aisef2.product.contract import BehaviorContract, Subject  # noqa: E402
from aisef2.product.outcome import Executed, IndeterminateReason  # noqa: E402
from tests.v2 import ledgerlock_candidate as LL  # noqa: E402
from tests.v2 import test_c2_file_artifact as base  # noqa: E402   (helpers only: its test classes are not imported)

REQUIRES, DECIDABLE = SubjectAbsence.REQUIRES_SUBJECT, SubjectAbsence.ABSENCE_IS_DECIDABLE
FA = SubjectKind.FILE_ARTIFACT
HEX = "ab" * 32
REQ = Requirement.create(id="R-1", text="the package holds nothing outside the standard library", source="docs/requirements.md 1")
GREP = {"grep": "^import socket", "suffixes": [".py"]}
IMPORTS = {"imports_outside": {"stdlib": True, "allowed": []}}
WITHIN = {"matches": 0, "within_s": 30}

#: id -> (kind, locator, stimulus, observable, subject_absence). A python_imports contract cannot be in a bundle 2.0.0
#: wrote (the class came with capability 2): the fixture says what the mechanism does with a spec id a release record
#: of capability 1 names for one, which is what a record for a later release would hold.
CONTRACTS = {
    # counts: PM-9 selects those whose absence the contract requires, PM-11 selects every one
    "BC-GREP-DIR-REQ": (FA, "path:pkg", GREP, WITHIN, REQUIRES),
    "BC-IMPORTS-DIR-REQ": (FA, "path:pkg", IMPORTS, WITHIN, REQUIRES),
    "BC-GREP-NOSUFFIX-REQ": (FA, "path:pkg", {"grep": "x"}, WITHIN, REQUIRES),     # reads every file
    "BC-GREP-UNUSED-REQ": (FA, "path:other", GREP, WITHIN, REQUIRES),              # no criterion names it
    "BC-GREP-FILE-REQ": (FA, "path:pkg/mod.py", GREP, {"matches": 1, "within_s": 30}, REQUIRES),     # names a .py file
    "BC-GREP-DIR-DEC": (FA, "path:pkg", GREP, WITHIN, DECIDABLE),      # PM-9 leaves it (zero matches stays the verdict)
    # not selected by any declared change: the class is not a count; another probe
    "BC-EXISTS-REQ": (FA, "path:pkg/mod.py", {}, {"condition": "exists", "within_s": 30}, REQUIRES),
    "BC-CALLABLE-REQ": (SubjectKind.PYTHON_CALLABLE, "app.calc:add", {"args": [2, 3]}, {"returns": 5, "within_s": 10}, REQUIRES),
}
COUNTS = {"BC-GREP-DIR-REQ", "BC-IMPORTS-DIR-REQ", "BC-GREP-NOSUFFIX-REQ", "BC-GREP-UNUSED-REQ", "BC-GREP-FILE-REQ",
          "BC-GREP-DIR-DEC"}
SELECTED = COUNTS                      # as file_artifact declares its changes: PM-9 and PM-11
SELECTED_BY_PM9 = COUNTS - {"BC-GREP-DIR-DEC"}
NOT_SELECTED = set(CONTRACTS) - SELECTED
USED = set(CONTRACTS) - {"BC-GREP-UNUSED-REQ"}


def contract(cid: str) -> BehaviorContract:
    kind, locator, stimulus, observable, absence = CONTRACTS[cid]
    return BehaviorContract.create(id=cid, requirement_ids=(REQ.id,), subject=Subject(kind, locator),
                                   stimulus=stimulus, observable=observable, polarity=Polarity.MUST_HOLD,
                                   subject_absence=absence, rationale=f"fixture {cid}")


def era_bundle(release: str | None = "2.0.0", *, spec_id=None, extra_approvals=()) -> dict:
    """A bundle whose plan names the spec ids `release` compiled (None: this release's), every contract approved by
    `human:fixture-owner` — the shape a 2.0.0 bundle has, without a 2.0.0 bundle. `spec_id` overrides the id of every
    obligation."""
    refs = {k: bundle_cli.ProbeRef(e.probe_id, e.probe_digest) for k, e in catalog.active().items()}
    contracts = [contract(cid) for cid in CONTRACTS]
    approvals = [ContractApproval(REQ.id, REQ.requirement_hash, c.id, c.contract_hash, "human:fixture-owner", 100.0 + n, ())
                 for n, c in enumerate(contracts)]
    obligations, facts = [], {}
    for c in (c for c in contracts if c.id in USED):
        spec = bundle_cli._mint(c, refs[c.subject.kind])
        sid = spec_id or (bundle_cli._earlier(spec, bundle_cli.RELEASES[release]) if release else spec.id)
        crit = f"C-{c.id[3:]}"
        obligations.append(PlanObligation(crit, sid, "S1", ObligationRole.INTRODUCE,
                                          EXPECTED_AT_PARENT[ObligationRole.INTRODUCE], (), f"S1 introduces {crit}"))
        facts[crit] = {"requirement": REQ.id, "section": "1", "clause": "1.1", "clause_text": REQ.text,
                       "subject": c.subject.locator}
    plan = Plan.create(id="PLAN-FIXTURE", baseline="a" * 40, obligations=tuple(obligations),
                       plan_quality_policy=NOT_PREREGISTERED)
    return B.dump(name="fixture", description="a bundle of an earlier release", requirements_path="docs/requirements.md",
                  requirements_sha256=HEX, product_roots=("pkg",), requirements=(REQ,), contracts=contracts,
                  approvals=[*approvals, *extra_approvals], plan=plan, facts=facts,
                  stories={"S1": {"depends_on": [], "tests": ["tests/test_pkg.py"]}})


def release_with(version: int, *, probe_id: str | None = None, digest: str = HEX, compiler: str = "f" * 64) -> dict:
    """A release record like 2.0.0's whose file_artifact is at capability `version` (and, to be a probe of another id,
    `probe_id`): its ids differ from this release's by the compiler digest, so a plan of it is migrated."""
    rel = copy.deepcopy(dict(bundle_cli.RELEASES["2.0.0"]))
    rel["compiler_digest"] = compiler
    rel["probes"][FA] = (probe_id or fa.PROBE_ID, digest, version)
    return rel


def run_main(*argv) -> tuple[int, dict | None, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = bundle_cli.main([str(a) for a in argv])
    return code, (json.loads(out.getvalue()) if out.getvalue().strip() else None), err.getvalue()


def follow(test: unittest.TestCase, report: dict, candidate: dict, approver: str = "human:fixture-reviewer") -> dict:
    """What the owner does with the report: the candidate is written where the first printed command reads it, each
    command is run as printed — only the placeholder approver replaced — and the file the last one wrote is read back.
    Where a shell splits a command as POSIX does, the printed words are the arguments."""
    rows = report["needs_owner_reapproval"]["contracts"]
    pathlib.Path(rows[0]["reads"]).write_text(json.dumps(candidate), encoding="utf-8")
    for row in rows:
        argv = ["bundle", "approve", row["reads"], "--contract", row["contract"], "--approver", bundle_cli.PLACEHOLDER,
                "--out", row["writes"]]
        if sys.platform != "win32":
            test.assertEqual(shlex.split(row["command"]), ["aisef", *argv])
        code, printed, err = run_main(*[approver if w == bundle_cli.PLACEHOLDER else w for w in argv[1:]])
        test.assertEqual(code, 0, err)
        test.assertEqual(printed["approved"], row["contract"])
    return json.loads(pathlib.Path(rows[-1]["writes"]).read_text(encoding="utf-8"))


def with_entry(**changes):
    """`catalog.active` as it is, the file_artifact entry replaced with these fields changed."""
    real = catalog.active

    def active(*a, **k):
        table = dict(real(*a, **k))
        table[FA] = dataclasses.replace(table[FA], **changes)
        return table
    return mock.patch.object(catalog, "active", active)


# ----------------------------------------------------------------------------------------------- the declarations


class Declarations(unittest.TestCase):
    """What a probe says it changed is held to a form the reader takes — and to the probe."""

    def test_every_probe_of_the_catalog_declares_every_capability_version_above_1(self):
        for e in catalog.CATALOG:
            with self.subTest(e.probe_id):
                if e.capability_version is None:
                    self.assertFalse(e.active, "an active probe declares its CAPABILITY_VERSION: its changes cannot be read otherwise")
                    continue
                self.assertEqual(e.capability_version, sys.modules[e.factory.__module__].CAPABILITY_VERSION)
                self.assertGreaterEqual(e.capability_version, 1)
                declared = e.capability_changes or {}
                self.assertEqual(set(declared) - set(range(2, e.capability_version + 1)), set(),
                                 "a record for a version this probe is not at (or for 1, which changed nothing)")
                for version in range(2, e.capability_version + 1):
                    self.assertIsNotNone(bundle_cli._declared(e, version),
                                         f"{e.probe_id} capability {version}: no well formed record in CAPABILITY_CHANGES")

    def test_the_catalog_entry_is_what_the_module_declares(self):
        for e in catalog.CATALOG:
            mod = sys.modules[e.factory.__module__]
            with self.subTest(e.probe_id):
                self.assertEqual(e.capability_version, getattr(mod, "CAPABILITY_VERSION", None))
                self.assertIs(e.capability_changes, getattr(mod, "CAPABILITY_CHANGES", None))

    def test_each_release_records_a_capability_version_the_current_probe_can_be_compared_with(self):
        """RELEASES holds, for each probe of a release, its id, its digest and the capability version it was at (2.0.0:
        version 1, the classes of the tag: the counter came after it). A version above the current one, or none, would make
        `migrate` read no change at all, or a negative range."""
        active = {e.subject_kind: e for e in catalog.active().values()}
        for name, release in bundle_cli.RELEASES.items():
            for kind, (probe_id, digest, version) in release["probes"].items():
                with self.subTest(release=name, kind=kind.value):
                    self.assertIsInstance(version, int)
                    self.assertGreaterEqual(version, 1)
                    self.assertRegex(digest, r"^[0-9a-f]{64}$")
                    if kind in active and active[kind].probe_id == probe_id:
                        self.assertLessEqual(version, active[kind].capability_version)

    def test_a_record_the_reader_cannot_take_is_none_and_never_nothing_changed(self):
        e = next(x for x in catalog.CATALOG if x.probe_id == fa.PROBE_ID)
        good = {"summary": "s", "affects": ({"classes": ("grep_count",), "when": "w", "before": "b", "after": "a"},)}
        cases = {"no record": {}, "a summary that is empty": {3: {**good, "summary": ""}},
                 "no affects": {3: {"summary": "s"}}, "an unknown key": {3: {**good, "other": 1}},
                 "a selector without its after": {3: {"summary": "s", "affects": ({"when": "w", "before": "b"},)}},
                 "a class the probe does not have": {3: {"summary": "s", "affects": (
                     {**good["affects"][0], "classes": ("grep_counts",)},)}},
                 "a subject_absence that is none": {3: {"summary": "s", "affects": (
                     {**good["affects"][0], "subject_absence": ("SOMETIMES",)},)}},
                 "a key no selector has (a function)": {3: {"summary": "s", "affects": (
                     {**good["affects"][0], "applies_to": lambda i: True},)}},
                 "a selector that is not an object": {3: {"summary": "s", "affects": ("grep_count",)}},
                 "classes that are empty": {3: {"summary": "s", "affects": ({**good["affects"][0], "classes": ()},)}},
                 # a record the reader cannot take is None whatever its members are: none of these is an exception
                 "a class that is a list (unhashable)": {3: {"summary": "s", "affects": (
                     {**good["affects"][0], "classes": (["grep_count"],)},)}},
                 "a subject_absence that is a dict (unhashable)": {3: {"summary": "s", "affects": (
                     {**good["affects"][0], "subject_absence": ({"REQUIRES_SUBJECT": 1},)},)}},
                 "a class that is a number": {3: {"summary": "s", "affects": ({**good["affects"][0], "classes": (3,)},)}},
                 "classes that are a bare string": {3: {"summary": "s", "affects": (
                     {**good["affects"][0], "classes": "grep_count"},)}},
                 "a when that is not text": {3: {"summary": "s", "affects": ({**good["affects"][0], "when": 3},)}},
                 "a ref that is empty": {3: {"summary": "s", "affects": ({**good["affects"][0], "ref": ""},)}},
                 "a ref that is not text": {3: {"summary": "s", "affects": ({**good["affects"][0], "ref": 9},)}},
                 "an affects that is a mapping": {3: {"summary": "s", "affects": good["affects"][0]}}}
        self.assertIsNotNone(bundle_cli._declared(dataclasses.replace(e, capability_changes={3: good}), 3))
        self.assertIsNotNone(bundle_cli._declared(dataclasses.replace(e, capability_changes={
            3: {**good, "affects": ({**good["affects"][0], "ref": "PM-9"},)}}), 3))      # a ref is allowed
        for label, changes in cases.items():
            with self.subTest(label):
                self.assertIsNone(bundle_cli._declared(dataclasses.replace(e, capability_changes=changes), 3))
        for label, changes in {"none": None, "a list": [good], "a tuple of pairs": ((3, good),), "a number": 3}.items():
            with self.subTest(label):
                self.assertIsNone(bundle_cli._declared(dataclasses.replace(e, capability_changes=changes), 3))

    def test_file_artifact_declares_what_pm9_and_pm11_changed_and_what_the_python_imports_class_did_not(self):
        self.assertEqual(fa.CAPABILITY_VERSION, 3)
        self.assertEqual(set(fa.CAPABILITY_CHANGES), {2, 3})
        self.assertEqual(fa.CAPABILITY_CHANGES[2]["affects"], ())      # a class was added: no contract that existed changed
        pm9, pm11 = fa.CAPABILITY_CHANGES[3]["affects"]
        self.assertEqual((set(pm9["classes"]), set(pm9["subject_absence"])),
                         ({"grep_count", "python_imports"}, {"REQUIRES_SUBJECT"}))
        for word in ("INDETERMINATE", "PRECONDITION_ABSENT"):
            self.assertIn(word, pm9["after"])
        for word in ("SATISFIED", "REFUTED"):
            self.assertIn(word, pm9["before"])
        self.assertTrue(pm9["when"].startswith("PM-9") and pm11["when"].startswith("PM-11"))
        self.assertNotIn("subject_absence", pm11)       # a count is read through the mark whatever the contract says of absence
        self.assertEqual(set(pm11["classes"]), {"grep_count", "python_imports"})

    def test_the_pm9_after_is_what_the_probe_gives_and_a_decidable_absence_keeps_its_verdict(self):
        """The record says: a path in the tree that selects no file, under REQUIRES_SUBJECT, is INDETERMINATE
        (PRECONDITION_ABSENT) — and under ABSENCE_IS_DECIDABLE it keeps the verdict of zero matches; a count over a file
        the suffixes take is observed. The probe, run over a directory, says that."""
        probe = fa.FileArtifactProbe()
        with tempfile.TemporaryDirectory(prefix="aisef2-capability-") as t:
            d = pathlib.Path(t)
            for rel, data in (("docs/readme.md", b"import socket\n"), ("pkg/mod.py", b"x = 1\n")):
                (d / rel).parent.mkdir(parents=True, exist_ok=True)
                (d / rel).write_bytes(data)
            at = RevisionRef("0" * 40, str(d))
            indeterminate = Executed(BehaviorVerdict.INDETERMINATE, IndeterminateReason.PRECONDITION_ABSENT)
            for stimulus, observable in ((GREP, WITHIN), (IMPORTS, WITHIN)):
                with self.subTest(stimulus=stimulus):
                    s = base.spec("path:docs", observable, stimulus, absence=REQUIRES)
                    self.assertEqual(run_probe(probe, s, at, base.ENV).result, indeterminate)
                    s = base.spec("path:docs", observable, stimulus, absence=DECIDABLE)
                    self.assertEqual(run_probe(probe, s, at, base.ENV).result, Executed(BehaviorVerdict.SATISFIED))
                    s = base.spec("path:pkg/mod.py", observable, stimulus, absence=REQUIRES)
                    self.assertEqual(run_probe(probe, s, at, base.ENV).result, Executed(BehaviorVerdict.SATISFIED))

    def test_the_pm11_before_and_after_are_what_the_text_gives_and_what_the_probe_gives(self):
        """The record says: a start-anchored pattern did not match line 1 of a file that begins with the mark (the reading
        of 2.0.0, `decode("utf-8")`), and now does (the mark is dropped). The two readings are compared on the text, and
        the probe, run over a directory holding such a file, gives the second."""
        raw = b"\xef\xbb\xbfimport socket\nx = 1\n"
        pattern = re.compile(GREP["grep"])
        self.assertEqual([bool(pattern.search(line)) for line in raw.decode("utf-8").splitlines()[:1]], [False])
        self.assertEqual([bool(pattern.search(line)) for line in raw.decode("utf-8-sig").splitlines()[:1]], [True])
        probe = fa.FileArtifactProbe()
        with tempfile.TemporaryDirectory(prefix="aisef2-capability-") as t:
            d = pathlib.Path(t)
            (d / "pkg").mkdir()
            (d / "pkg/mod.py").write_bytes(raw)
            s = base.spec("path:pkg", WITHIN, GREP, absence=DECIDABLE)       # a prohibition, ABSENCE_IS_DECIDABLE: PM-9 leaves it
            self.assertEqual(run_probe(probe, s, RevisionRef("0" * 40, str(d)), base.ENV).result,
                             Executed(BehaviorVerdict.REFUTED))     # 2.0.0 read zero matches and satisfied it

    def test_before_and_after_must_be_non_empty_text_or_the_record_is_none(self):
        """`before`/`after` are the lineage text `_assess` puts in the operator's carry-over report (one per selected
        contract); an empty or non-text one is not a well formed record, so `_declared` is None and the change fails
        closed over every contract, never narrowed by a blank selector that would carry a stale approval over."""
        e = next(x for x in catalog.CATALOG if x.probe_id == fa.PROBE_ID)
        good = {"summary": "s", "affects": ({"classes": ("grep_count",), "when": "w", "before": "b", "after": "a"},)}
        self.assertIsNotNone(bundle_cli._declared(dataclasses.replace(e, capability_changes={3: good}), 3))
        for field in ("before", "after"):
            for label, bad in (("empty", ""), ("not text", 3)):
                changes = {3: {"summary": "s", "affects": ({**good["affects"][0], field: bad},)}}
                with self.subTest(field=field, value=label):
                    self.assertIsNone(bundle_cli._declared(dataclasses.replace(e, capability_changes=changes), 3))


# ----------------------------------------------------------------------------------------------- the migration


class WhatMigrateWithholds(unittest.TestCase):
    def setUp(self) -> None:
        self.doc = era_bundle()
        self.before = copy.deepcopy(self.doc)
        self.out, self.report = bundle_cli.migrate(self.doc)

    def withheld(self, why=None) -> set[str]:
        return {r["contract"] for r in self.report["approvals_withheld"] if why in (None, r["why"])}

    def test_the_input_is_history_and_is_never_written(self):
        self.assertEqual(self.doc, self.before)
        self.assertIsNot(self.out["approvals"], self.doc["approvals"])

    def test_exactly_the_contracts_a_declared_change_selects_are_withheld(self):
        self.assertEqual(self.withheld(), SELECTED)
        self.assertEqual({r["why"] for r in self.report["approvals_withheld"]}, {"semantic"})
        self.assertEqual({c["contract"] for c in self.report["semantic_changes"]}, SELECTED)
        self.assertEqual({c["contract"] for c in self.report["needs_owner_reapproval"]["contracts"]}, SELECTED)

    def test_a_class_that_is_no_count_and_another_probe_are_kept(self):
        kept = {a["contract_id"] for a in self.out["approvals"]}
        self.assertEqual(kept, NOT_SELECTED)
        self.assertEqual(self.report["approvals_kept"], len(NOT_SELECTED))

    def test_each_contract_names_the_changes_that_select_it(self):
        """PM-9 selects a count whose absence the contract requires, PM-11 every count: a decidable absence is selected
        by PM-11 alone. A path that names a .py file is selected by both, because a selector reads the contract's class
        and absence and not its path (a directory can bear a file's name): the `when` beside each says which condition
        the repository must meet."""
        tags = {c["contract"]: [h["ref"] for h in c["changes"]] for c in self.report["semantic_changes"]}
        self.assertEqual(tags["BC-GREP-DIR-REQ"], ["PM-9", "PM-11"])
        self.assertEqual(tags["BC-GREP-FILE-REQ"], ["PM-9", "PM-11"])
        self.assertEqual(tags["BC-GREP-DIR-DEC"], ["PM-11"])
        for c in self.report["semantic_changes"]:
            for h in c["changes"]:
                self.assertTrue(h["when"].startswith(h["ref"] + ":"), (c["contract"], h["ref"]))

    def test_the_candidate_keeps_only_approvals_the_input_held_untouched_and_signs_nothing(self):
        for a in self.out["approvals"]:
            self.assertIn(a, self.before["approvals"])
        self.assertEqual({a["approver"] for a in self.out["approvals"]}, {"human:fixture-owner"})
        self.assertEqual({k: v for k, v in self.out.items() if k not in ("plan", "approvals")},
                         {k: v for k, v in self.before.items() if k not in ("plan", "approvals")})
        self.assertNotIn("approvals", self.report["unchanged"])
        self.assertLessEqual({"requirements", "contracts", "facts", "stories", "requirements_document"},
                             set(self.report["unchanged"]))

    def test_the_candidate_lacks_exactly_what_was_withheld_and_does_not_load(self):
        self.assertEqual({x["contract"] for x in bundle_cli.unapproved(self.out)}, SELECTED)
        with self.assertRaises(B.BundleError) as c:
            B.load(self.out)
        self.assertIn("is not approved", str(c.exception))
        self.assertEqual(self.report["candidate"]["contracts_to_approve"], len(SELECTED))
        self.assertFalse(self.report["candidate"]["loads"])

    def test_the_report_says_where_it_comes_from_and_when_the_verdict_differs(self):
        rows = {c["contract"]: c for c in self.report["semantic_changes"]}
        row = rows["BC-GREP-DIR-REQ"]
        self.assertEqual((row["probe"], row["class"], row["subject_absence"]), (fa.PROBE_ID, "grep_count", "REQUIRES_SUBJECT"))
        self.assertEqual(row["from"], {"release": "2.0.0", "capability_version": 1})
        self.assertEqual(row["to"], {"capability_version": fa.CAPABILITY_VERSION})
        self.assertEqual({c["version"] for c in row["changes"]}, {3})       # version 2 was declared to change nothing
        self.assertEqual(len(row["changes"]), 2)                            # version 3 selects it twice: PM-9 and PM-11
        for change in row["changes"]:
            for k in ("summary", "when", "before", "after"):
                self.assertTrue(change[k], k)
        self.assertEqual(rows["BC-IMPORTS-DIR-REQ"]["class"], "python_imports")
        [given] = row["approvals_in_input"]        # the approval kept in the input, as history: who and when
        self.assertEqual((given["approver"], given["approved_at"]), ("human:fixture-owner", 100.0))
        self.assertEqual(given["contract_hash"], contract("BC-GREP-DIR-REQ").contract_hash)

    def test_the_report_gives_the_ground_of_every_approval_it_keeps(self):
        """Not a count: for each group of kept approvals, the probe, class and absence, the capability versions it was
        read between, the records consulted, and why none selected it."""
        rows = self.report["approvals_kept_grounds"]
        kept = {a["contract_id"] for a in self.out["approvals"]}
        self.assertEqual(sorted(c for r in rows for c in r["contracts"]), sorted(kept))      # each once, none other
        by = {(r["probe"], r["class"]): r for r in rows}
        exists = by[(fa.PROBE_ID, "exists")]
        self.assertEqual((exists["from"], exists["to"]), ({"release": "2.0.0", "capability_version": 1},
                                                          {"capability_version": fa.CAPABILITY_VERSION}))
        self.assertEqual([(c["version"], c["selectors"]) for c in exists["consulted"]], [(2, 0), (3, 2)])
        self.assertTrue(all(c["summary"] for c in exists["consulted"]))
        self.assertIn("none selects class exists", exists["ground"])
        unmoved = by[("probe.python_callable_v2", "returns")]
        self.assertEqual((unmoved["consulted"], unmoved["from"]["capability_version"], unmoved["to"]["capability_version"]),
                         ([], 1, 1))
        self.assertIn("did not move", unmoved["ground"])      # nothing was read because nothing could have been declared
        for r in rows:
            self.assertTrue(r["ground"] and r["contracts"])

    def test_the_report_says_what_the_rule_cannot_see(self):
        text = " ".join(self.report["limits"])
        for words in ("identity rule", "ARCHITECTURE-EXCEPTION-V2-007", "without moving its CAPABILITY_VERSION",
                      "never the repository", "earlier build of `migrate`"):
            self.assertIn(words, text)

    def test_the_contract_no_criterion_names_takes_the_bundle_s_release(self):
        self.assertIn("BC-GREP-UNUSED-REQ", self.withheld())

    def test_the_candidate_is_identified_by_the_digest_load_calls_the_bundle_s(self):
        candidate = self.report["candidate"]
        written = json.loads(json.dumps(self.out, indent=1, sort_keys=True))
        self.assertEqual(candidate["bundle_digest"], hashlib.sha256(B._canonical(written)).hexdigest())
        self.assertEqual(candidate["plan_hash"], self.out["plan"]["plan_hash"])
        self.assertEqual(candidate["plan_hash"], self.report["plan_hash"]["to"])
        self.assertEqual((candidate["contracts"], candidate["approvals_kept"]), (len(CONTRACTS), len(NOT_SELECTED)))
        approved = LL.approved(self.out, self.report)
        self.assertEqual(B.load(approved).digest, hashlib.sha256(B._canonical(approved)).hexdigest())
        self.assertNotEqual(B.load(approved).digest, candidate["bundle_digest"])    # each approval is a new bundle

    def test_the_printed_commands_name_the_candidate_and_chain_and_the_bundle_then_loads(self):
        """The commands are paste-ready: the candidate's own path (the one given to `migrate`), the file each writes and
        the next reads, `lint` for the last — only the approver is left to the operator."""
        with tempfile.TemporaryDirectory() as t:
            here = pathlib.Path(t) / "candidate.json"
            candidate, report = bundle_cli.migrate(self.before)
            report = bundle_cli.with_commands(report, here)
            rows = report["needs_owner_reapproval"]["contracts"]
            self.assertIn("nothing was signed", report["needs_owner_reapproval"]["how"])
            self.assertEqual(rows[0]["reads"], str(here))
            self.assertEqual([r["reads"] for r in rows[1:]], [r["writes"] for r in rows[:-1]])
            self.assertEqual(len({r["writes"] for r in rows}), len(rows))
            self.assertEqual(report["needs_owner_reapproval"]["then"], f"aisef bundle lint {bundle_cli._shell_word(rows[-1]['writes'])}")
            for row in rows:
                self.assertEqual(row["contract_hash"], contract(row["contract"]).contract_hash)
            done = follow(self, report, candidate)
            self.assertEqual(len(B.load(done).approvals), len(CONTRACTS))
            self.assertEqual(bundle_cli.unapproved(done), [])

    def test_a_printed_command_pasted_as_it_is_signs_nothing(self):
        """`human:NAME` is a placeholder, not a person: the kernel takes any `human:<name>`, so `approve` refuses this one."""
        with tempfile.TemporaryDirectory() as t:
            here = pathlib.Path(t) / "candidate.json"
            candidate, report = bundle_cli.migrate(self.before)
            report = bundle_cli.with_commands(report, here)
            here.write_text(json.dumps(candidate), encoding="utf-8")
            row = report["needs_owner_reapproval"]["contracts"][0]
            code, printed, err = run_main("approve", row["reads"], "--contract", row["contract"],
                                          "--approver", bundle_cli.PLACEHOLDER, "--out", row["writes"])
            self.assertEqual((code, printed), (2, None))
            self.assertIn("placeholder", err)
            self.assertFalse(pathlib.Path(row["writes"]).exists())
            with self.assertRaises(B.BundleError):
                bundle_cli.approve(candidate, row["contract"], bundle_cli.PLACEHOLDER, 1.0)

    def test_the_candidate_has_two_digests_and_each_says_what_it_is_of(self):
        """`bundle_digest` is what `load` gives the project (canonical JSON), not the sha256 of the file written;
        `migrate` through the command adds the file's."""
        with tempfile.TemporaryDirectory() as t:
            src, out = pathlib.Path(t) / "in.json", pathlib.Path(t) / "candidate.json"
            src.write_text(json.dumps(self.before), encoding="utf-8")
            code, printed, err = run_main("migrate", src, "--out", out)
            self.assertEqual((code, err), (0, ""))
            c = printed["candidate"]
            self.assertEqual(c["file_sha256"], hashlib.sha256(out.read_bytes()).hexdigest())
            self.assertEqual(c["bundle_digest"], hashlib.sha256(B._canonical(json.loads(out.read_text(encoding="utf-8")))).hexdigest())
            self.assertNotEqual(c["file_sha256"], c["bundle_digest"])
            self.assertIn("canonical", c["bundle_digest_is"])
            self.assertTrue(printed["needs_owner_reapproval"]["contracts"][0]["reads"].endswith("candidate.json"))
            self.assertEqual(printed["needs_owner_reapproval"]["contracts"][0]["reads"], str(out))

    def test_the_kept_ground_rows_carry_the_absence_group_and_a_reason(self):
        """approvals_kept_grounds is the owner's record of why each carried-over approval was kept: every row holds the
        full group identity (subject_absence among it) and a non-empty ground. A bundle already of this release has one
        row whose ground says there is no earlier release to compare against."""
        FIELDS = {"probe", "class", "subject_absence", "from", "to", "consulted", "ground", "contracts"}
        rows = self.report["approvals_kept_grounds"]
        for r in rows:
            self.assertEqual(set(r), FIELDS, r)                     # no field dropped and no key emptied
        exists = next(r for r in rows if (r["probe"], r["class"]) == (fa.PROBE_ID, "exists"))
        self.assertEqual(exists["subject_absence"], "REQUIRES_SUBJECT")   # the absence group the owner reads
        [current] = bundle_cli.migrate(era_bundle(release=None))[1]["approvals_kept_grounds"]
        self.assertEqual(set(current), FIELDS, current)
        self.assertIn("no earlier release whose capability to compare", current["ground"])

    def test_the_ground_of_each_kept_approval_names_the_contract_s_own_absence(self):
        """key[2] of `_group` carries the contract's declared subject_absence into each grounds row, so the owner
        reads, per group, under which absence `no change selects it` held. It is the contract's own absence, never the
        release the approval was read from (2.0.0 here)."""
        rows = self.report["approvals_kept_grounds"]
        declared = {cid: contract(cid).subject_absence.value for cid in NOT_SELECTED}
        self.assertEqual({c for r in rows for c in r["contracts"]}, set(declared))
        for r in rows:
            for cid in r["contracts"]:
                self.assertEqual(r["subject_absence"], declared[cid], cid)
        by = {(r["probe"], r["class"]): r for r in rows}
        self.assertEqual(by[(fa.PROBE_ID, "exists")]["subject_absence"], "REQUIRES_SUBJECT")
        self.assertEqual(by[("probe.python_callable_v2", "returns")]["subject_absence"], "REQUIRES_SUBJECT")

    def test_with_commands_defaults_the_file_names_each_approval_and_passes_a_clean_report_through(self):
        """The approve commands are shaped only here, and the CLI's own tests compare their output to `with_commands`
        itself, so these literals are pinned nowhere else. With no --out the first command reads `candidate.json` (the
        documented default); each file written is `<stem>.approved-N<suffix>`; `how` tells the operator to run them in
        order and that the placeholder is refused; and a report needing no reapproval is returned (not dropped to None),
        which `main` then subscripts for `candidate.file_sha256`."""
        report = bundle_cli.with_commands(copy.deepcopy(self.report))        # no out: the documented default path
        rows = report["needs_owner_reapproval"]["contracts"]
        self.assertEqual(rows[0]["reads"], "candidate.json")
        self.assertEqual([r["writes"] for r in rows],
                         [f"candidate.approved-{n}.json" for n in range(1, len(rows) + 1)])
        how = report["needs_owner_reapproval"]["how"]
        self.assertIn("run them in order", how)
        self.assertIn("refuses the placeholder", how)
        clean = bundle_cli.migrate(era_bundle(release=None))[1]
        self.assertIsNone(clean["needs_owner_reapproval"])
        passed = bundle_cli.with_commands(clean)
        self.assertIsInstance(passed, dict)
        self.assertEqual(passed["candidate"], clean["candidate"])           # passed through; main reads it next


class WhatIsNotKept(unittest.TestCase):
    """The bundle is approved at the contracts' hashes; an approval that does not bind them has no ground to be kept."""

    def test_an_approval_that_no_longer_binds_is_not_carried_and_is_named(self):
        stale = ContractApproval(REQ.id, REQ.requirement_hash, "BC-EXISTS-REQ", "0" * 64, "human:old", 5.0, ())
        gone = ContractApproval(REQ.id, REQ.requirement_hash, "BC-REMOVED", HEX, "human:old", 6.0, ())
        out, report = bundle_cli.migrate(era_bundle(extra_approvals=(stale, gone)))
        unbound = {(r["contract"], r["approver"]) for r in report["approvals_withheld"] if r["why"] == "unbound"}
        self.assertEqual(unbound, {("BC-EXISTS-REQ", "human:old"), ("BC-REMOVED", "human:old")})
        self.assertEqual({a["approver"] for a in out["approvals"]}, {"human:fixture-owner"})
        self.assertEqual({c["contract"] for c in report["semantic_changes"]}, SELECTED)      # not "semantic"
        self.assertEqual({x["contract"] for x in bundle_cli.unapproved(out)}, SELECTED)

    def test_a_bundle_already_of_this_release_loses_nothing(self):
        doc = era_bundle(release=None)
        out, report = bundle_cli.migrate(doc)
        self.assertEqual(out, doc)
        [ground] = report["approvals_kept_grounds"]
        self.assertEqual((ground["from"], ground["probe"], len(ground["contracts"])), ({"release": "current"}, None, len(CONTRACTS)))
        self.assertEqual((report["specs_rebound"], report["approvals_withheld"], report["semantic_changes"],
                          report["needs_owner_reapproval"]), (0, [], [], None))
        self.assertEqual(report["unchanged"], ["requirements", "contracts", "approvals", "facts", "stories",
                                               "requirements_document"])
        self.assertTrue(report["candidate"]["loads"])
        B.load(out)

    def test_a_release_already_at_the_current_version_changed_nothing_since(self):
        with mock.patch.dict(bundle_cli.RELEASES, {"as-current": release_with(fa.CAPABILITY_VERSION)}):
            doc = era_bundle("as-current")
            out, report = bundle_cli.migrate(doc)
        self.assertEqual({r["from_release"] for r in report["mapping"].values()}, {"as-current"})
        self.assertEqual((report["approvals_withheld"], out["approvals"]), ([], doc["approvals"]))
        B.load(out)

    def test_only_the_versions_after_the_release_s_are_read(self):
        """Capability 2 (python_imports, nothing changed) to 3 (PM-9): version 3 selects; from 3 nothing is read."""
        for version, selected in ((1, True), (2, True), (3, False)):
            with self.subTest(release_version=version), \
                    mock.patch.dict(bundle_cli.RELEASES, {"r": release_with(version)}):
                _, report = bundle_cli.migrate(era_bundle("r"))
                self.assertEqual({r["contract"] for r in report["approvals_withheld"]}, SELECTED if selected else set())

    def test_a_declared_record_of_a_version_that_changed_nothing_withholds_nothing(self):
        only_python_imports_added = {2: fa.CAPABILITY_CHANGES[2]}
        with with_entry(capability_changes=only_python_imports_added, capability_version=2), \
                mock.patch.dict(bundle_cli.RELEASES, {"r": release_with(1)}):
            _, report = bundle_cli.migrate(era_bundle("r"))
        self.assertEqual(report["approvals_withheld"], [])


def only(*selectors) -> dict:
    """The declarations of file_artifact with version 3 holding just these selectors."""
    return {2: fa.CAPABILITY_CHANGES[2], 3: {"summary": "s", "affects": tuple(selectors)}}


class EachDeclaredChangeSelectsByItself(unittest.TestCase):
    PM9, PM11 = fa.CAPABILITY_CHANGES[3]["affects"]

    def withheld(self, *selectors) -> set[str]:
        with with_entry(capability_changes=only(*selectors)):
            _, report = bundle_cli.migrate(era_bundle())
        return {r["contract"] for r in report["approvals_withheld"]}

    def test_pm9_selects_the_counts_whose_absence_the_contract_requires(self):
        got = self.withheld(self.PM9)
        self.assertEqual(got, SELECTED_BY_PM9)
        self.assertNotIn("BC-GREP-DIR-DEC", got)      # ABSENCE_IS_DECIDABLE: zero matches was and is its verdict
        self.assertFalse(got & {"BC-EXISTS-REQ", "BC-CALLABLE-REQ"})

    def test_pm11_selects_every_count_whatever_it_says_of_absence(self):
        got = self.withheld(self.PM11)
        self.assertEqual(got, COUNTS)
        self.assertFalse(got & {"BC-EXISTS-REQ", "BC-CALLABLE-REQ"})

    def test_a_change_that_names_a_class_no_contract_has_selects_nothing(self):
        sel = {**self.PM9, "classes": ("python_imports",), "subject_absence": ("ABSENCE_IS_DECIDABLE",)}
        self.assertEqual(self.withheld(sel), set())      # no python_imports contract is decidable

    def test_a_selector_without_classes_or_absence_selects_every_contract_of_the_probe(self):
        sel = {k: v for k, v in self.PM9.items() if k not in ("classes", "subject_absence")}
        self.assertEqual(self.withheld(sel), {cid for cid, row in CONTRACTS.items() if row[0] is FA})


class FailClosed(unittest.TestCase):
    """What is not declared is not "nothing changed": it selects every contract of its probe."""

    FILE_ARTIFACT = {cid for cid, row in CONTRACTS.items() if row[0] is FA}

    def withheld_with(self, release="2.0.0", **changes) -> set[str]:
        with with_entry(**changes):
            _, report = bundle_cli.migrate(era_bundle(release))
        return {r["contract"] for r in report["approvals_withheld"]}

    def test_a_version_with_no_record_selects_every_contract_of_the_probe(self):
        got = self.withheld_with(capability_changes={2: fa.CAPABILITY_CHANGES[2]})      # 3 is not declared
        self.assertEqual(got, self.FILE_ARTIFACT)
        self.assertNotIn("BC-CALLABLE-REQ", got)       # the other probes are not at fault

    def test_no_declarations_at_all_is_the_same(self):
        self.assertEqual(self.withheld_with(capability_changes=None), self.FILE_ARTIFACT)
        self.assertEqual(self.withheld_with(capability_changes={}), self.FILE_ARTIFACT)

    def test_a_record_that_is_not_well_formed_is_the_same(self):
        bad = {2: fa.CAPABILITY_CHANGES[2], 3: {"summary": "x", "affects": ({"classes": ("grep_count",)},)}}
        self.assertEqual(self.withheld_with(capability_changes=bad), self.FILE_ARTIFACT)

    def test_a_record_with_an_unhashable_member_is_the_same_and_migrate_does_not_raise(self):
        """The case that used to be a TypeError out of migrate: a class written as a list."""
        bad = {2: fa.CAPABILITY_CHANGES[2], 3: {"summary": "x", "affects": ({"classes": (["grep_count"],), "when": "w",
                                                                              "before": "b", "after": "a"},)}}
        self.assertEqual(self.withheld_with(capability_changes=bad), self.FILE_ARTIFACT)
        self.assertEqual(self.withheld_with(capability_changes=[fa.CAPABILITY_CHANGES[2]]), self.FILE_ARTIFACT)

    def test_a_probe_with_no_capability_version_is_the_same(self):
        self.assertEqual(self.withheld_with(capability_version=None), self.FILE_ARTIFACT)

    def test_an_undeclared_change_is_said_in_the_report_as_such(self):
        with with_entry(capability_changes={2: fa.CAPABILITY_CHANGES[2]}):
            _, report = bundle_cli.migrate(era_bundle())
        [change] = next(c for c in report["semantic_changes"] if c["contract"] == "BC-EXISTS-REQ")["changes"]
        self.assertEqual(change["version"], 3)
        self.assertIn("no well formed record", change["summary"])

    def test_a_probe_that_is_not_the_one_the_release_used_cannot_be_compared(self):
        release = release_with(1, probe_id="probe.file_artifact_of_the_past", digest="cd" * 32)
        with mock.patch.dict(bundle_cli.RELEASES, {"r": release}):
            _, report = bundle_cli.migrate(era_bundle("r"))
        self.assertEqual({r["contract"] for r in report["approvals_withheld"]}, self.FILE_ARTIFACT)
        [change] = next(c for c in report["semantic_changes"] if c["contract"] == "BC-EXISTS-REQ")["changes"]
        self.assertIn("not comparable", change["summary"])

    def test_each_fail_closed_change_row_is_the_whole_report_structure(self):
        """A fail-closed row is what the report hands the owner to justify a withheld approval (semantic_changes, and
        seal's approvals_withheld_semantic): the six fields, the `every`-use wording that says the difference was not
        ruled out, and the case's reason, not a lone summary. Checked for every withheld contract of each case."""
        KEYS = {"version", "ref", "when", "before", "after", "summary"}
        WHEN = "every use of the probe"
        BEFORE = "as the earlier release evaluated it"
        AFTER = "as this release evaluates it: the difference is not declared, so it is not ruled out"
        with with_entry(capability_version=None):
            _, no_version = bundle_cli.migrate(era_bundle())
        with with_entry(capability_changes={2: fa.CAPABILITY_CHANGES[2]}):      # 3 undeclared
            _, undeclared = bundle_cli.migrate(era_bundle())
        past = release_with(1, probe_id="probe.file_artifact_of_the_past", digest="cd" * 32)
        with mock.patch.dict(bundle_cli.RELEASES, {"r": past}):
            _, not_comparable = bundle_cli.migrate(era_bundle("r"))
        cases = {"no capability version": (no_version, "declares no capability version"),
                 "no well formed record": (undeclared, "no well formed record"),
                 "not comparable": (not_comparable, "not comparable")}
        for label, (report, phrase) in cases.items():
            self.assertEqual({c["contract"] for c in report["semantic_changes"]}, self.FILE_ARTIFACT, label)
            rows = [h for c in report["semantic_changes"] for h in c["changes"]]
            self.assertTrue(rows, label)
            for h in rows:
                with self.subTest(label, ref=h.get("ref")):
                    self.assertEqual(set(h), KEYS)      # the whole row: no field dropped, renamed or extra
                    self.assertEqual((h["when"], h["before"], h["after"]), (WHEN, BEFORE, AFTER))
                    self.assertIsNone(h["ref"])
                    self.assertIn(phrase, h["summary"])


class NoContractIsNamed(unittest.TestCase):
    def test_the_mechanism_names_no_contract_of_any_bundle(self):
        for rel in ("aisef2/app/bundle_cli.py", "aisef2/probe/file_artifact.py", "aisef2/probe/catalog.py"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            with self.subTest(rel):
                for word in ("BC-V22", "LedgerLock", "ledgerlock"):
                    self.assertNotIn(word, text, f"{rel} names {word}: what is withheld is derived, not listed")

    def test_the_six_come_out_of_the_declarations_by_class_and_absence(self):
        """Every contract of the LedgerLock bundle read as bound under 2.0.0: nine are file_artifact; the six that are
        counts under REQUIRES_SUBJECT are selected (PM-9 and PM-11 each), the three existence checks and the other
        probes are not selected at all."""
        doc = LL.read()
        contracts = {c["id"]: BehaviorContract.from_json(c) for c in doc["contracts"]}
        specs = {cid: bundle_cli._mint(c, bundle_cli._refs()[c.subject.kind]) for cid, c in contracts.items()}
        exposed = bundle_cli._exposure(contracts, specs, {cid: "2.0.0" for cid in contracts})
        self.assertEqual(set(exposed), LEDGERLOCK_COUNTS)
        self.assertEqual({c.id for c in contracts.values() if c.subject.kind is FA},
                         LEDGERLOCK_COUNTS | {"BC-V22-S-13-a", "BC-V22-S-13-b", "BC-V22-S-13-c"})
        for cid in LEDGERLOCK_COUNTS:
            self.assertEqual([h["when"].split(":")[0] for h in exposed[cid]["changes"]], ["PM-9", "PM-11"])


# ----------------------------------------------------------------------------------------------- LedgerLock


#: the contracts of the 2.0.0 LedgerLock bundle that are grep_count under REQUIRES_SUBJECT: four over the directory
#: `ledgerlock`, two over one .py file (listed here to check the mechanism's answer against, never read by it)
LEDGERLOCK_COUNTS = {"BC-V22-S-10-a", "BC-V22-S-10-b", "BC-V22-S-10-c", "BC-V22-S-12-a", "BC-V22-S-12-b", "BC-V22-S-12-c"}


class TheLedgerLockBundle(unittest.TestCase):
    """The committed 2.0.0 bundle, read only; the candidate and everything approved on it live in scratch."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.doc = LL.read()
        cls.out, cls.report = bundle_cli.migrate(json.loads(json.dumps(cls.doc)))

    def test_exactly_six_of_the_59_approvals_are_withheld_and_the_rest_are_kept(self):
        self.assertEqual(len(self.doc["approvals"]), 59)
        self.assertEqual({r["contract"] for r in self.report["approvals_withheld"]}, LEDGERLOCK_COUNTS)
        self.assertEqual(len(self.report["approvals_withheld"]), 6)
        self.assertEqual(self.report["approvals_kept"], 53)
        self.assertEqual(self.out["approvals"], [a for a in self.doc["approvals"] if a["contract_id"] not in
                                                 {r["contract"] for r in self.report["approvals_withheld"]}])
        for row in self.report["semantic_changes"]:
            self.assertEqual((row["class"], row["subject_absence"], row["from"]["release"]),
                             ("grep_count", "REQUIRES_SUBJECT", "2.0.0"))
        self.assertEqual({r["subject"] for r in self.report["semantic_changes"]},
                         {"file_artifact path:ledgerlock", "file_artifact path:ledgerlock/ledger.py",
                          "file_artifact path:ledgerlock/cli.py"})
        for row in self.report["approvals_withheld"]:       # the approval stays in the input, as history: who and when
            self.assertEqual(row["approver"], "human:owner")

    def test_the_ground_of_the_53_kept_approvals_is_read_not_counted(self):
        rows = self.report["approvals_kept_grounds"]
        self.assertEqual(sum(len(r["contracts"]) for r in rows), 53)
        self.assertEqual({r["probe"] for r in rows}, {fa.PROBE_ID, "probe.cli_invocation", "probe.process_effect",
                                                      "probe.python_callable_v2"})
        for r in rows:
            if r["probe"] != fa.PROBE_ID:
                # their capability version is the release's: nothing is declared for them, and the report says so
                self.assertEqual((r["from"]["capability_version"], r["to"]["capability_version"], r["consulted"]), (1, 1, []))
                self.assertIn("did not move", r["ground"])
            else:
                self.assertEqual([c["version"] for c in r["consulted"]], [2, 3])
        counts = {p: sum(len(r["contracts"]) for r in rows if r["probe"] == p) for p in {r["probe"] for r in rows}}
        self.assertEqual(counts, {fa.PROBE_ID: 3, "probe.cli_invocation": 10, "probe.process_effect": 34,
                                  "probe.python_callable_v2": 6})

    def test_the_plan_is_rebound_as_it_always_was(self):
        self.assertEqual((self.report["specs_rebound"], self.report["obligations"]), (59, 67))
        self.assertEqual(self.report["plan_hash"]["from"], self.doc["plan"]["plan_hash"])
        self.assertEqual(self.report["plan_hash"]["to"], self.out["plan"]["plan_hash"])
        self.assertNotEqual(self.report["plan_hash"]["from"], self.report["plan_hash"]["to"])

    def test_the_candidate_lints_not_ready_with_exactly_those_six_and_ready_once_they_are_approved(self):
        now = {e.probe_id: executing(e.factory) for e in catalog.CATALOG if e.active}
        rows = tuple(dict(r, probe_digest=now.get(r["probe_id"], r["probe_digest"])) for r in CALIBRATIONS)
        calibrated = R.calibrations(rows)      # each shipped row re-bound to the bytes that run now: the table's rows, as test_v21_identity
        with mock.patch.object(R, "calibrations", lambda *a: calibrated):
            lint = bundle_cli.lint(self.out)
            self.assertEqual(lint["verdict"], "NOT_READY")
            self.assertEqual({x["contract"] for x in lint["to_approve"]},
                             {r["contract"] for r in self.report["approvals_withheld"]})
            self.assertEqual(len(lint["to_approve"]), 6)
            self.assertIn("not run", lint["admission"])
            self.assertEqual(lint["criteria_without_calibration"], [])
            with tempfile.TemporaryDirectory() as t:
                candidate, report = bundle_cli.migrate(json.loads(json.dumps(self.doc)))
                done = follow(self, bundle_cli.with_commands(report, pathlib.Path(t) / "candidate.json"), candidate,
                              "human:scratch-stand-in")
            ready = bundle_cli.lint(done)
        self.assertEqual((ready["verdict"], ready["to_approve"]), ("READY", []))
        self.assertTrue(ready["admission"]["admitted"], ready["admission"])
        self.assertEqual(B.load(done).plan.plan_hash, self.report["plan_hash"]["to"])
        self.assertEqual(len(done["approvals"]), 59)
        # what the scratch bundle holds of the owner's is exactly what the owner's bundle held, and nothing else
        self.assertEqual([a for a in done["approvals"] if a["approver"] != "human:scratch-stand-in"], self.out["approvals"])

    def test_the_command_prints_the_report_and_exits_0_for_a_migration_performed(self):
        with tempfile.TemporaryDirectory() as t:
            out = pathlib.Path(t) / "candidate.json"
            code, printed, err = run_main("migrate", LL.LEDGERLOCK_2_0_0, "--out", out)
            self.assertEqual((code, err), (0, ""))
            self.assertEqual(printed["written"], str(out))
            self.assertEqual(printed["approvals_kept"], 53)
            self.assertEqual(printed["candidate"]["bundle_digest"],
                             hashlib.sha256(B._canonical(json.loads(out.read_text(encoding="utf-8")))).hexdigest())
            self.assertEqual(len(printed["needs_owner_reapproval"]["contracts"]), 6)
            self.assertEqual(code, 0)
            code, _, err = run_main("lint", out)
            self.assertEqual(code, 1, err)          # NOT_READY until the owner approves
        self.assertEqual(self.doc, LL.read())      # the committed bundle is as it was


# ----------------------------------------------------------------------------------------------- seal


class SealKeepsTheSameRule(unittest.TestCase):
    """`seal --keep-approvals-from OLD`: the approvals of OLD that still bind are kept, those of a contract a declared
    change evaluates differently since OLD's release are not, and each is named."""

    @staticmethod
    def authoring() -> dict:
        contracts = []
        for cid in CONTRACTS:
            j = contract(cid).to_json()
            contracts.append({k: j[k] for k in bundle_cli.CONTRACT_KEYS})
        criteria = [{"id": f"C-{cid[3:]}", "contract": cid, "role": "INTRODUCE", "depends_on": [], "why": f"S1 introduces {cid}",
                     "facts": {"requirement": REQ.id, "section": "1", "clause": "1.1", "clause_text": REQ.text,
                               "subject": CONTRACTS[cid][1]}} for cid in CONTRACTS if cid in USED]
        return {"format": bundle_cli.AUTHORING_FORMAT, "name": "fixture", "description": "d",
                "requirements_document": {"path": "docs/requirements.md", "sha256": HEX}, "product_roots": ["pkg"],
                "baseline": "a" * 40, "requirements": [{"id": REQ.id, "text": REQ.text, "source": REQ.source}],
                "contracts": contracts,
                "stories": {"S1": {"depends_on": [], "tests": ["tests/test_pkg.py"], "criteria": criteria}}}

    def seal(self, old: dict, **kw):
        return bundle_cli.seal(self.authoring(), approvals=old["approvals"], exposed=bundle_cli.exposure_of(old), **kw)

    def test_an_approval_of_a_selected_contract_is_not_kept_and_is_named(self):
        _, report = self.seal(era_bundle())
        self.assertEqual({r["contract"] for r in report["approvals_withheld_semantic"]}, SELECTED)
        self.assertEqual(report["approvals_kept"], len(NOT_SELECTED))
        self.assertEqual(report["approvals_dropped"], [])
        self.assertEqual({x["contract"] for x in report["to_approve"]}, SELECTED)
        row = next(r for r in report["approvals_withheld_semantic"] if r["contract"] == "BC-GREP-DIR-REQ")
        self.assertEqual((row["approver"], row["changes"][0]["version"]), ("human:fixture-owner", 3))

    def test_approvals_handed_over_without_their_exposure_are_refused(self):
        """The library does not keep by hash alone: a caller that hands `seal` approvals says what is exposed (the
        command does, from the bundle they come from), and `exposed={}` is the statement that none is."""
        old = era_bundle()
        with self.assertRaises(B.BundleError) as c:
            bundle_cli.seal(self.authoring(), approvals=old["approvals"])
        self.assertIn("exposed", str(c.exception))
        with self.assertRaises(B.BundleError):
            bundle_cli.seal(self.authoring(), approvals=iter(old["approvals"]))        # a generator is as many
        _, report = bundle_cli.seal(self.authoring())                                  # no approvals: nothing to be told
        self.assertEqual(report["approvals_kept"], 0)
        _, report = bundle_cli.seal(self.authoring(), approvals=old["approvals"], exposed={})
        self.assertEqual(report["approvals_kept"], len(CONTRACTS))
        self.assertEqual(self.seal(old)[1]["approvals_kept"], len(NOT_SELECTED))       # the rule, as the command applies it

    def test_an_old_bundle_of_this_release_loses_nothing(self):
        _, report = self.seal(era_bundle(release=None))
        self.assertEqual((report["approvals_withheld_semantic"], report["approvals_kept"], report["to_approve"]),
                         ([], len(CONTRACTS), []))

    def test_an_old_bundle_whose_plan_no_release_compiles_is_read_from_the_earliest_capability(self):
        old = era_bundle(spec_id="PPS-" + "f" * 64)
        self.assertEqual(set(bundle_cli.exposure_of(old)), SELECTED)

    def test_the_command_writes_a_bundle_without_those_approvals(self):
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t)
            (t / "old.json").write_text(json.dumps(era_bundle()), encoding="utf-8")
            (t / "authoring.json").write_text(json.dumps(self.authoring()), encoding="utf-8")
            code, printed, err = run_main("seal", t / "authoring.json", "--keep-approvals-from", t / "old.json",
                                          "--out", t / "new.json")
            self.assertEqual(code, 0, err)
            self.assertEqual({r["contract"] for r in printed["approvals_withheld_semantic"]}, SELECTED)
            written = json.loads((t / "new.json").read_text(encoding="utf-8"))
            self.assertEqual({a["contract_id"] for a in written["approvals"]}, NOT_SELECTED)

    def test_the_report_without_an_old_bundle_names_nothing(self):
        _, report = bundle_cli.seal(self.authoring())
        self.assertEqual((report["approvals_withheld_semantic"], report["approvals_kept"]), ([], 0))

    def test_each_withheld_row_names_the_binding_and_its_provenance(self):
        """An operator re-approves and audits from this row, not the contract alone: every withheld row names which
        requirement the approval bound and when it was approved. Full key set, and each field against the input
        approval it reports."""
        old = era_bundle()
        _, report = self.seal(old)
        by_contract = {a["contract_id"]: a for a in old["approvals"]}
        rows = report["approvals_withheld_semantic"]
        self.assertEqual({r["contract"] for r in rows}, SELECTED)       # rows exist to check
        for r in rows:
            self.assertEqual(set(r), {"contract", "requirement", "approver", "approved_at", "changes"})
            a = by_contract[r["contract"]]
            self.assertEqual((r["requirement"], r["approver"], r["approved_at"]),
                             (a["requirement_id"], a["approver"], a["approved_at"]))


class TheOldBundleMustBeOne(unittest.TestCase):
    def test_a_bundle_to_keep_approvals_from_that_does_not_load_is_refused_before_anything_is_written(self):
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t)
            (t / "old.json").write_text(json.dumps({"approvals": []}), encoding="utf-8")
            (t / "authoring.json").write_text(json.dumps(SealKeepsTheSameRule.authoring()), encoding="utf-8")
            code, _, err = run_main("seal", t / "authoring.json", "--keep-approvals-from", t / "old.json",
                                    "--out", t / "new.json")
            self.assertEqual(code, 2)
            self.assertIn("refused", err)
            self.assertFalse((t / "new.json").exists())


if __name__ == "__main__":
    unittest.main()
