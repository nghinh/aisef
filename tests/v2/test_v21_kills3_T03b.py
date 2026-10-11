"""Mutation-survivor kills, batch T03b: `aisef bundle migrate` (aisef2/app/bundle_cli.py::migrate).

`migrate` re-binds a 2.0.0 bundle's plan to this release's spec ids and returns (the bundle, the report); the command
prints the report as JSON beside the path it wrote. What the operator relies on, and what this file holds:

* the report's `unchanged` is the scope statement "nothing but the plan changed, no re-approval needed" (USAGE-2.1 §2);
* the report's `mapping` is the audit trail old spec id -> new spec id, and the release that compiled the old one;
* a bundle that cannot be re-bound is refused as a MigrationError (never a raw KeyError / TypeError / PlanError), and
  the refusal says which stage failed and why, with the count / the contract it is about;
* the table of earlier releases takes more than one entry: an id two releases compile keeps its first attribution,
  and a refusal names every release it tried as its own token.

Offline; no probe runs. Uses the committed 2.0.0 LedgerLock bundle (59 specs, 67 obligations)."""

from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import os
import pathlib
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle as B  # noqa: E402
from aisef2.app import bundle_cli  # noqa: E402
from aisef2.arch.enums import SubjectKind  # noqa: E402
from aisef2.plan.obligation import Plan  # noqa: E402
from aisef2.probe import catalog  # noqa: E402
from aisef2.product.contract import BehaviorContract, Subject, plain  # noqa: E402

LEDGERLOCK_2_0_0 = ROOT / "closure-evidence/v2/release/LEDGERLOCK-PROJECT.json"


class _LedgerLock(unittest.TestCase):
    """A fresh copy of the 2.0.0 bundle per test; `migrate` is given copies so an in-place edit would show."""

    def setUp(self) -> None:
        self.doc = json.loads(LEDGERLOCK_2_0_0.read_text(encoding="utf-8"))

    def fresh(self) -> dict:
        return json.loads(json.dumps(self.doc))

    def with_unknown_specs(self, n: int) -> tuple[dict, list[str]]:
        """The bundle whose first `n` obligations name a spec no release compiles, and their criterion ids."""
        plan = B._plan(self.doc["plan"])
        obligations = [dataclasses.replace(o, product_proof_spec_id="PPS-" + str(i) * 64) if i < n else o
                       for i, o in enumerate(plan.obligations)]
        sealed = Plan.create(id=plan.id, baseline=plan.baseline, obligations=tuple(obligations),
                             plan_quality_policy=plan.plan_quality_policy)
        return {**self.doc, "plan": plain(sealed)}, [o.criterion_id for o in plan.obligations[:n]]


class ReportScopeStatement(_LedgerLock):
    """The report's `unchanged` says which sections of the bundle migration left as they were. Reader: the operator
    (the command prints the report); the guarantee itself is `{**data, "plan": ...}` and `B.load(out)`, the list
    declares it. Pins aisef2/app/bundle_cli.py::migrate [20, 38, 41, 42, 43, 44, 45, 46, 55, 56, 57, 58, 59, 60]."""

    #: USAGE-2.1 §2: "requirement, contract, approval, facts: unchanged; nothing is re-approved"
    DOCUMENTED = {"requirements", "contracts", "approvals", "facts"}
    #: also declared by the report, and asserted untouched by tests/v2/test_v21_identity.py::Migrate: the stories the
    #: plan's story ids must match (B.load) and the requirements document the run checks at the baseline
    ALSO_STATED = {"stories", "requirements_document"}

    def test_every_section_the_report_names_is_a_bundle_section_left_as_it_was(self):
        out, report = bundle_cli.migrate(self.fresh())
        self.assertIn("unchanged", report)
        named = report["unchanged"]
        self.assertEqual(len(named), len(set(named)), named)
        self.assertEqual(set(named) - set(B.KEYS), set(), "named, but no section of a bundle")
        for section in named:
            self.assertEqual(out[section], self.doc[section], section)
        self.assertNotIn("plan", named)
        self.assertEqual({k for k in out if out[k] != self.doc[k]}, {"plan"})     # the one section that did change

    def test_the_report_names_the_sections_migration_leaves_as_they_were(self):
        _, report = bundle_cli.migrate(self.fresh())
        self.assertLessEqual(self.DOCUMENTED | self.ALSO_STATED, set(report["unchanged"]))

    def test_the_command_prints_the_report_beside_the_path_it_wrote(self):
        with tempfile.TemporaryDirectory() as t:
            target = pathlib.Path(t) / "migrated.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(bundle_cli.main(["migrate", os.fspath(LEDGERLOCK_2_0_0), "--out",
                                                  os.fspath(target)]), 0)
            printed = json.loads(stdout.getvalue())
            self.assertEqual(printed, {"written": os.fspath(target), **bundle_cli.migrate(self.fresh())[1]})
        self.assertLessEqual(self.DOCUMENTED | self.ALSO_STATED, set(printed["unchanged"]))


class ReportMapping(_LedgerLock):
    """The report's `mapping` is the audit trail of every re-bound spec: old id -> {to: new id, from_release}. The
    oracle is the two plans compared obligation by obligation, not the report itself.
    Pins aisef2/app/bundle_cli.py::migrate [50, 71]."""

    def test_each_rebound_spec_is_mapped_to_its_new_id_and_the_release_that_compiled_the_old(self):
        out, report = bundle_cli.migrate(self.fresh())
        before, after = B._plan(self.doc["plan"]), B._plan(out["plan"])
        self.assertEqual([o.criterion_id for o in before.obligations], [o.criterion_id for o in after.obligations])
        expected = {a.product_proof_spec_id: {"to": b.product_proof_spec_id, "from_release": "2.0.0"}
                    for a, b in zip(before.obligations, after.obligations, strict=True)
                    if a.product_proof_spec_id != b.product_proof_spec_id}
        self.assertEqual(len(expected), 59)
        self.assertEqual(report["mapping"], expected)
        self.assertEqual(report["specs_rebound"], len(report["mapping"]))
        # the new ids are the specs this release compiles from the bundle's approved contracts
        self.assertLessEqual({v["to"] for v in report["mapping"].values()}, set(B.load(out).specs))


class KernelObjectsThatDoNotLoad(_LedgerLock):
    """A bundle whose requirements, contracts, approvals or plan do not construct is refused as a MigrationError that
    names the stage and the cause (class and detail), whichever of KeyError / TypeError / ValueError the kernel
    raised; the exception is kept as __cause__. Through the API the caller must not see a raw KeyError or PlanError.
    Pins aisef2/app/bundle_cli.py::migrate [26, 27, 28, 77, 78]."""

    def test_each_kind_of_construction_failure_is_a_migration_error_naming_stage_and_cause(self):
        cases = (
            ("a requirement without its id", {"requirements": [{"no_id": 1}]}, KeyError),
            ("a requirement field the kernel does not know", {"requirements": [{"id": "R", "bogus": 1}]}, TypeError),
            ("a plan whose hash does not bind its content",
             {"plan": {**self.doc["plan"], "plan_hash": "0" * 64}}, ValueError),
        )
        for label, edit, kind in cases:
            with self.subTest(label):
                with self.assertRaises(bundle_cli.MigrationError) as c:
                    bundle_cli.migrate({**self.doc, **edit})
                cause = c.exception.__cause__
                self.assertIsInstance(cause, kind)
                text = str(c.exception)
                self.assertIn("kernel objects do not load", text)      # the stage, as B.load names it
                # the cause's class and its detail, separable: something between them (the stage's own prefix and the
                # separator are not the contract), never `KeyError'id'`
                self.assertRegex(text, re.escape(type(cause).__name__) + r"\W+" + re.escape(str(cause)))


class ContractThatDoesNotCompile(_LedgerLock):
    """A contract the kernel cannot compile is refused as a MigrationError that names the contract, says that it does
    not compile, and gives the compiler's own reason. The contract is named by migrate itself: the compiler's reason
    does not always carry it (no probe for the subject kind). Pins aisef2/app/bundle_cli.py::migrate [81]."""

    def refusal(self, doc: dict, contract_id: str, cause_type: type) -> None:
        with self.assertRaises(bundle_cli.MigrationError) as c:
            bundle_cli.migrate(doc)
        cause = c.exception.__cause__
        self.assertIsInstance(cause, cause_type)
        text = str(c.exception)
        self.assertIn(contract_id, text)            # the refused object
        self.assertIn("does not compile", text)     # the stage: not the plan, not the kernel objects
        self.assertIn(str(cause), text)             # the compiler's own reason
        return cause

    def test_the_refusal_names_the_contract_the_stage_and_the_reason(self):
        contract_id = self.doc["contracts"][0]["id"]
        self.refusal({**self.doc, "approvals": []}, contract_id, ValueError)      # no approval binds it

    def test_the_contract_is_named_even_when_the_compilers_reason_does_not(self):
        inactive = [k for k in SubjectKind if k not in catalog.active()]
        if not inactive:
            self.skipTest("every subject kind has an active probe in this release")
        first = BehaviorContract.from_json(self.doc["contracts"][0])
        retargeted = BehaviorContract.create(
            id=first.id, requirement_ids=first.requirement_ids, subject=Subject(inactive[0], "GET /ledger"),
            stimulus=first.stimulus, observable=first.observable, polarity=first.polarity,
            subject_absence=first.subject_absence, rationale=first.rationale)
        doc = bundle_cli.approve({**self.doc, "contracts": [retargeted.to_json(), *self.doc["contracts"][1:]]},
                                 first.id, "human:reviewer", 0.0)       # approved: the one thing wrong is the probe
        cause = self.refusal(doc, first.id, ValueError)
        self.assertNotIn(first.id, str(cause))      # so migrate's own naming is what is read


class SpecNoKnownReleaseCompiles(_LedgerLock):
    """An obligation naming a spec that no release compiles from the bundle's approved contracts is refused, never
    guessed. The refusal says how many obligations (with their unit), which criteria, and which releases were tried.
    Pins aisef2/app/bundle_cli.py::migrate [73]."""

    def test_the_refusal_gives_the_count_the_criteria_and_the_release_tried(self):
        doc, criteria = self.with_unknown_specs(2)
        with self.assertRaises(bundle_cli.MigrationError) as c:
            bundle_cli.migrate(doc)
        text = str(c.exception)
        counted = re.search(r"(?<![\w.])(\d+)\s+obligation", text)      # the number, as its own token, with its unit
        self.assertIsNotNone(counted, text)
        self.assertEqual(int(counted.group(1)), 2)
        for criterion in criteria:
            self.assertIn(criterion, text)
        for release in bundle_cli.RELEASES:
            self.assertRegex(text, rf"\b{re.escape(release)}\b")
        self.assertIn("no known release", text)


class MoreThanOneRelease(_LedgerLock):
    """`RELEASES` is built to take more than the one entry it ships with. With a second entry that compiles to the
    same ids as the first (a later release whose probes did not change): the first release keeps the attribution of
    every id both compile, and the unknown-spec refusal names each release as its own token.
    Pins aisef2/app/bundle_cli.py::migrate [49, 82]."""

    def two_releases(self):
        return mock.patch.dict(bundle_cli.RELEASES, {"alias": dict(bundle_cli.RELEASES["2.0.0"])})

    def test_an_id_two_releases_both_compile_stays_attributed_to_the_first(self):
        once = bundle_cli.migrate(self.fresh())
        with self.two_releases():
            self.assertEqual(list(bundle_cli.RELEASES), ["2.0.0", "alias"])
            twice = bundle_cli.migrate(self.fresh())
        self.assertEqual(twice, once)
        self.assertEqual({v["from_release"] for v in twice[1]["mapping"].values()}, {"2.0.0"})

    def test_the_unknown_spec_refusal_names_each_release_as_its_own_token(self):
        doc, _ = self.with_unknown_specs(1)
        with self.two_releases():
            with self.assertRaises(bundle_cli.MigrationError) as c:
                bundle_cli.migrate(doc)
            tried = list(bundle_cli.RELEASES)
        self.assertEqual(tried, ["2.0.0", "alias"])
        for name in tried:
            self.assertRegex(str(c.exception), rf"\b{re.escape(name)}\b")


if __name__ == "__main__":
    unittest.main()
