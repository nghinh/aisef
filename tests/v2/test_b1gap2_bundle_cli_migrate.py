"""Mutation kill tests for `aisef2/app/bundle_cli.py::migrate` (B1 gap batch 2, v2.2 release gate).

One test per surviving mutant of the campaign's audit:

* the L418 accounting gate: a bundle with two contracts under one id (the variant's approval withheld `unbound`,
  `unapproved(candidate)` iterating the contracts LIST) makes `lacks != owed` while the withheld count still balances —
  the gate's `or` leg must raise, and the raise must be a MigrationError (not a KeyError out of its own f-string);
* the report rows an owner and the next tool read: `approvals_withheld[].requirement_hash`,
  `semantic_changes[].{requirements,polarity,observable,stimulus}` and their keys, `needs_owner_reapproval` rows'
  `requirements`, the sorted order of both arrays, and `candidate.plan_id` — each pinned to an oracle that is not the
  code under test (the fixture's own contracts and plan).

Fixtures are `tests/v2/test_v21_migrate_semantics.py`'s (helpers only: its test classes are not imported).
Offline; no provider; no probe runs a subject."""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle_cli  # noqa: E402
from aisef2.arch.enums import Polarity  # noqa: E402
from aisef2.product.approval import ContractApproval  # noqa: E402
from aisef2.product.contract import BehaviorContract, Subject, plain  # noqa: E402
from tests.v2.test_v21_migrate_semantics import (  # noqa: E402  (fixtures only, no test class imported)
    CONTRACTS, REQ, SELECTED, contract, era_bundle,
)


def twinned() -> dict:
    """A bundle of this release with a second contract under the id BC-EXISTS-REQ — the same fields, another rationale,
    so another contract_hash — inserted FIRST (the loader's contracts dict last-wins), and its own approval appended.
    Shape and load accept it; the twin's approval no longer binds the surviving contract and is withheld `unbound`;
    `unapproved(candidate)` iterates the contracts LIST and sees the twin unapproved. So at L418 `lacks != owed`
    ({(BC-EXISTS-REQ, R-1)} vs set()) while the count leg balances (kept + withheld == input): only the gate's first
    leg refuses it."""
    doc = era_bundle(None)
    kind, locator, stimulus, observable, absence = CONTRACTS["BC-EXISTS-REQ"]
    twin = BehaviorContract.create(id="BC-EXISTS-REQ", requirement_ids=(REQ.id,), subject=Subject(kind, locator),
                                   stimulus=stimulus, observable=observable, polarity=Polarity.MUST_HOLD,
                                   subject_absence=absence, rationale="twin")
    doc["contracts"].insert(0, twin.to_json())
    doc["approvals"].append(plain(ContractApproval(REQ.id, REQ.requirement_hash, twin.id, twin.contract_hash,
                                                   "human:fixture-owner", 1.0, ())))
    return doc


class TheAccountingGate(unittest.TestCase):
    """L418-420: what the candidate lacks is exactly what was withheld, or migrate refuses — with a MigrationError."""

    # kills: L418 Or swapped
    def test_a_candidate_whose_lacks_are_not_the_withheld_is_refused(self):
        # the count leg is False here (kept + withheld == input), so under `and` the gate falls through and
        # migrate returns a candidate whose unapproved set the report does not account for
        with self.assertRaises(bundle_cli.MigrationError) as c:
            bundle_cli.migrate(twinned())
        self.assertIn("not what the withheld", str(c.exception))

    # kills: L420 string 'approvals' emptied
    def test_the_refusal_is_a_migration_error_and_not_its_own_message_failing(self):
        # the mutant turns len(data['approvals']) in the raise's f-string into len(data['']): a KeyError('')
        # escapes instead of the typed error a library caller's `except MigrationError` matches
        with self.assertRaises(bundle_cli.MigrationError):
            bundle_cli.migrate(twinned())


class TheReportRows(unittest.TestCase):
    """One migration of the 2.0.0-shaped fixture (six withheld, six semantic changes): each row field pinned to the
    fixture's own contracts, never to the report itself."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.out, cls.report = bundle_cli.migrate(era_bundle())

    def changes_row(self, cid: str) -> dict:
        rows = {c["contract"]: c for c in self.report["semantic_changes"]}
        self.assertEqual(set(rows), SELECTED)
        return rows[cid]

    # kills: L421 dict entry 5 dropped
    def test_each_withheld_approval_row_carries_the_requirement_hash_it_bound(self):
        rows = self.report["approvals_withheld"]
        self.assertEqual(len(rows), len(SELECTED))
        for r in rows:
            self.assertEqual(r["requirement_hash"], REQ.requirement_hash)

    # kills: L422 string 'requirement_hash' emptied
    def test_the_withheld_row_s_requirement_hash_is_under_its_own_key(self):
        for r in self.report["approvals_withheld"]:
            self.assertEqual(r["requirement_hash"], REQ.requirement_hash)
            self.assertNotIn("", r)

    # kills: L424 dict entry 1 dropped
    def test_each_semantic_change_row_names_the_contract_s_requirements(self):
        for row in self.report["semantic_changes"]:
            self.assertEqual(row["requirements"], [REQ.id])

    # kills: L424 string 'requirements' emptied
    def test_the_semantic_change_row_s_requirements_are_under_their_own_key(self):
        for row in self.report["semantic_changes"]:
            self.assertEqual(row["requirements"], [REQ.id])
            self.assertNotIn("", row)

    # kills: L424 dict entry 5 dropped
    def test_each_semantic_change_row_carries_the_contract_s_polarity(self):
        for row in self.report["semantic_changes"]:
            self.assertEqual(row["polarity"], contract(row["contract"]).polarity.value)

    # kills: L427 string 'polarity' emptied
    def test_the_semantic_change_row_s_polarity_is_under_its_own_key(self):
        row = self.changes_row("BC-GREP-DIR-REQ")
        self.assertEqual(row["polarity"], Polarity.MUST_HOLD.value)

    # kills: L424 dict entry 6 dropped
    def test_each_semantic_change_row_carries_the_contract_s_observable(self):
        row = self.changes_row("BC-GREP-DIR-REQ")
        self.assertEqual(row["observable"], contract("BC-GREP-DIR-REQ").to_json()["observable"])

    # kills: L428 string 'observable' emptied (the dict key: the subscript occurrence KeyErrors and was killed)
    def test_the_semantic_change_row_s_observable_is_under_its_own_key(self):
        row = self.changes_row("BC-GREP-DIR-REQ")
        self.assertEqual(row["observable"], contract("BC-GREP-DIR-REQ").to_json()["observable"])
        self.assertNotIn("", row)

    # kills: L424 dict entry 7 dropped
    def test_each_semantic_change_row_carries_the_contract_s_stimulus(self):
        row = self.changes_row("BC-GREP-DIR-REQ")
        self.assertEqual(row["stimulus"], contract("BC-GREP-DIR-REQ").to_json()["stimulus"])

    # kills: L428 string 'stimulus' emptied (the dict key: the subscript occurrence KeyErrors and was killed)
    def test_the_semantic_change_row_s_stimulus_is_under_its_own_key(self):
        row = self.changes_row("BC-GREP-DIR-REQ")
        self.assertEqual(row["stimulus"], contract("BC-GREP-DIR-REQ").to_json()["stimulus"])
        self.assertNotIn("", row)

    # kills: L429 sorted() -> list()
    def test_the_semantic_changes_are_in_sorted_contract_order(self):
        # insertion order (the fixture's CONTRACTS order: BC-GREP-DIR-DEC last) differs from sorted order
        self.assertEqual([c["contract"] for c in self.report["semantic_changes"]], sorted(SELECTED))

    # kills: L430 dict entry 1 dropped
    def test_each_reapproval_row_names_the_contract_s_requirements(self):
        rows = self.report["needs_owner_reapproval"]["contracts"]
        self.assertEqual(len(rows), len(SELECTED))
        for r in rows:
            self.assertEqual(r["requirements"], [REQ.id])

    # kills: L430 string 'requirements' emptied
    def test_the_reapproval_row_s_requirements_are_under_their_own_key(self):
        for r in self.report["needs_owner_reapproval"]["contracts"]:
            self.assertEqual(r["requirements"], [REQ.id])
            self.assertNotIn("", r)

    # kills: L431 sorted() -> list()
    def test_the_reapproval_rows_are_in_sorted_contract_order(self):
        self.assertEqual([c["contract"] for c in self.report["needs_owner_reapproval"]["contracts"]], sorted(SELECTED))

    # kills: L441 dict entry 2 dropped
    def test_the_candidate_names_the_plan_it_carries(self):
        self.assertEqual(self.report["candidate"]["plan_id"], self.out["plan"]["id"])

    # kills: L445 string 'plan_id' emptied
    def test_the_candidate_s_plan_id_is_under_its_own_key(self):
        self.assertEqual(self.report["candidate"]["plan_id"], self.out["plan"]["id"])
        self.assertNotIn("", self.report["candidate"])


if __name__ == "__main__":
    unittest.main()
