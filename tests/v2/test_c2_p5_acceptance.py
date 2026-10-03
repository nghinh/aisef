"""C2-P5 acceptance boundary: the real approvals are content-addressed, bound to the accepted proposal and given by the
established owner identity; a tampered or synthetic approval is refused; the acceptance re-derives on this tree."""

import copy
import dataclasses
import json
import unittest

from aisef2.plan.obligation import Plan
from validation.qualification import p5_acceptance as A


def _doc() -> dict:
    return json.loads((A.ROOT / A.APPROVALS_REL).read_text(encoding="utf-8"))


class Approvals(unittest.TestCase):
    def test_one_real_approval_per_retained_contract_by_the_owner(self):
        doc = _doc()
        self.assertEqual(A.approvals_problems(doc), [])
        self.assertEqual(doc["count"], 59)
        self.assertEqual({r["approver"] for r in doc["approvals"]}, {A.OWNER})
        self.assertEqual({r["contract_id"] for r in doc["approvals"]}, {c.id for c in A.contracts().values()})
        self.assertEqual(doc["binds"]["proposal_digest"], A.ACCEPTED["proposal_digest"])
        self.assertIn("closure-evidence/v2/AISEF-V2-RFC-APPROVAL.json", doc["approver_identity"]["established_by"])

    def test_a_tampered_approval_is_refused(self):
        doc = _doc()
        bad = copy.deepcopy(doc)
        bad["approvals"][0]["contract_hash"] = "0" * 64
        self.assertTrue(A.approvals_problems(bad))
        bad = copy.deepcopy(doc)
        bad["approvals"].pop()
        self.assertTrue(A.approvals_problems(bad))

    def test_a_synthetic_approver_is_refused(self):
        bad = copy.deepcopy(_doc())
        bad["approvals"][0]["approver"] = A._aid().SYNTHETIC_APPROVER
        problems = A.approvals_problems(bad)
        self.assertTrue(any("synthetic" in p for p in problems))
        self.assertTrue(any("is not human:owner" in p for p in problems))


class Acceptance(unittest.TestCase):
    def test_the_acceptance_re_derives_on_this_tree(self):
        self.assertEqual(A.check(), [])

    def test_the_admission_holds_only_under_every_real_approval(self):
        doc = json.loads((A.ROOT / A.OUT_REL).read_text(encoding="utf-8"))
        adm = doc["verification"]["admission"]
        self.assertEqual((adm["admitted"], adm["checks_passed"], adm["synthetic_approval_used"]), (True, 9, False))
        self.assertEqual(len(adm["approvals_given"]), 59)
        self.assertFalse(adm["one_approval_removed"]["admitted"])
        self.assertFalse(adm["no_approvals"]["admitted"])
        self.assertEqual(doc["verification"]["semantic_change"], "NONE")



class KernelProvenance(unittest.TestCase):
    """The proposal names the kernel it was authored on; only that field may differ after an authorized kernel change,
    and only when the committed value is the accepted candidate's kernel (owner, 2026-10-01)."""
    ACCEPTED_K, HEAD_K = "a" * 40, "b" * 40

    def _rec(self, tree, **identities):
        return {"proposal_digest": "d", "plan": {"plan_hash": "p"}, "identities": {"aisef2_tree": tree, "compiler": {"digest": "c"},
                                                                                     **identities}}

    def test_identical_records_are_current(self):
        r = A.proposal_currency(self._rec(self.ACCEPTED_K), self._rec(self.ACCEPTED_K), self.ACCEPTED_K, self.ACCEPTED_K)
        self.assertEqual((r["current"], r["differing_paths"]), (True, []))

    def test_only_the_provenance_differs_from_the_accepted_kernel_is_current(self):
        r = A.proposal_currency(self._rec(self.HEAD_K), self._rec(self.ACCEPTED_K), self.ACCEPTED_K, self.HEAD_K)
        self.assertEqual((r["current"], r["provenance_only"], r["differing_paths"]), (True, True, [A.PROVENANCE_PATH]))

    def test_a_committed_kernel_that_is_not_the_accepted_one_is_refused(self):
        r = A.proposal_currency(self._rec(self.HEAD_K), self._rec("c" * 40), self.ACCEPTED_K, self.HEAD_K)
        self.assertFalse(r["current"])

    def test_a_derived_kernel_that_is_not_this_tree_is_refused(self):
        r = A.proposal_currency(self._rec("c" * 40), self._rec(self.ACCEPTED_K), self.ACCEPTED_K, self.HEAD_K)
        self.assertFalse(r["current"])

    def test_any_semantic_difference_is_refused_with_or_without_the_provenance(self):
        for derived in (self._rec(self.HEAD_K, compiler={"digest": "x"}), self._rec(self.ACCEPTED_K, compiler={"digest": "x"})):
            r = A.proposal_currency(derived, self._rec(self.ACCEPTED_K), self.ACCEPTED_K, self.HEAD_K)
            self.assertFalse(r["current"])
            self.assertIn("identities.compiler.digest", r["differing_paths"])
        bad = self._rec(self.HEAD_K)
        bad["proposal_digest"] = "e"
        self.assertFalse(A.proposal_currency(bad, self._rec(self.ACCEPTED_K), self.ACCEPTED_K, self.HEAD_K)["current"])

    def test_the_authoring_aid_s_own_sha_is_tolerated_only_as_given(self):
        derived, committed = self._rec(self.HEAD_K), self._rec(self.ACCEPTED_K)
        derived["identities"]["authoring_aid"], committed["identities"]["authoring_aid"] = {"sha256": "n"}, {"sha256": "o"}
        self.assertFalse(A.proposal_currency(derived, committed, self.ACCEPTED_K, self.HEAD_K)["current"])
        self.assertFalse(A.proposal_currency(derived, committed, self.ACCEPTED_K, self.HEAD_K, aid=("x", "n"))["current"])
        r = A.proposal_currency(derived, committed, self.ACCEPTED_K, self.HEAD_K, aid=("o", "n"))
        self.assertEqual((r["current"], sorted(r["differing_paths"])), (True, sorted([A.AID_PATH, A.PROVENANCE_PATH])))
        self.assertIsNotNone(A.aid_provenance())        # on this tree: the aid changed in calibrations() alone

    def test_on_this_tree_the_committed_proposal_is_current(self):
        # up to the kernel provenance, the authoring aid's own sha (its calibrations() reads the release's shipped
        # calibrations) and the release's probe-identity re-binding (ProbeIdentityRebinding)
        r = A.current_proposal_currency()
        self.assertTrue(r["current"], r)
        self.assertTrue(r["document_current"], r)
        self.assertLessEqual(set(r["differing_paths"]), {A.PROVENANCE_PATH, A.AID_PATH})


class ProbeIdentityRebinding(unittest.TestCase):
    """The release's B1 moved three probe digests, hence the spec id and semantic hash of every spec on those probes,
    the plan hash and the proposal digest. The committed proposal is current up to probe identity
    (validation/qualification/rebind.py) — and nothing else may move with it: each case below changes one more thing
    and is refused."""

    @classmethod
    def setUpClass(cls):
        aid = A._aid()
        cls.plan = aid.build()["plan"]
        cls.committed = json.loads((A.ROOT / A.PROPOSAL_REL).read_text(encoding="utf-8"))
        cls.derived = aid.record()
        for k in ("aisef2_tree", "authoring_aid"):          # provenance as committed: what differs is the re-binding alone
            cls.derived["identities"][k] = cls.committed["identities"][k]
        cls.moved = next(i for i, (d, c) in enumerate(zip(cls.derived["specs"], cls.committed["specs"], strict=True))
                         if d["probe_digest"] != c["probe_digest"])

    def currency(self, derived, committed=None, plan=None):
        committed = committed or self.committed
        return A.proposal_currency(derived, committed, "k", "k", A.proposal_subst(derived, committed, plan or self.plan))

    def changed(self, **fields):
        d = copy.deepcopy(self.derived)
        d["specs"][self.moved].update(fields)
        return d

    def test_the_re_binding_alone_is_current(self):
        self.assertNotEqual(self.derived["plan"]["plan_hash"], self.committed["plan"]["plan_hash"])
        r = self.currency(self.derived)
        self.assertEqual((r["current"], r["differing_paths"]), (True, []))
        self.assertGreater(r["identities_rebound"], 0)

    def test_a_contract_hash_change_is_refused(self):
        r = self.currency(self.changed(contract_hash="0" * 64))
        self.assertFalse(r["current"])
        self.assertIn(f"specs[{self.moved}].contract_hash", r["differing_paths"])
        self.assertIn(f"specs[{self.moved}].spec_hash_id", r["differing_paths"])      # its identities are not re-bound

    def test_a_probe_id_change_is_refused(self):
        r = self.currency(self.changed(probe_id="probe.python_callable"))
        self.assertFalse(r["current"])
        self.assertIn(f"specs[{self.moved}].probe_id", r["differing_paths"])

    def test_a_re_derived_digest_that_is_not_this_tree_s_catalog_digest_is_refused(self):
        r = self.currency(self.changed(probe_digest="f" * 64))
        self.assertFalse(r["current"])
        self.assertIn(f"specs[{self.moved}].semantic_hash", r["differing_paths"])

    def test_a_mapped_back_hash_that_is_not_the_committed_is_refused(self):
        for path in (("plan", "plan_hash"), ("proposal_digest",)):
            committed = copy.deepcopy(self.committed)
            at = committed
            for k in path[:-1]:
                at = at[k]
            at[path[-1]] = "0" * 64
            with self.subTest(path=path):
                r = self.currency(self.derived, committed)
                self.assertFalse(r["current"])
                self.assertIn(".".join(path), r["differing_paths"])
        # a plan that differs beyond its spec ids: mapped back, its hash is not the accepted plan's
        o = self.plan.obligations[0]
        plan = Plan.create(id=self.plan.id, baseline=self.plan.baseline, plan_quality_policy=self.plan.plan_quality_policy,
                           obligations=(dataclasses.replace(o, ownership_rationale=o.ownership_rationale + " (edited)"),
                                        *self.plan.obligations[1:]))
        derived = copy.deepcopy(self.derived)
        derived["plan"]["plan_hash"] = plan.plan_hash
        r = self.currency(derived, plan=plan)
        self.assertFalse(r["current"])
        self.assertIn("plan.plan_hash", r["differing_paths"])


if __name__ == "__main__":
    unittest.main()
