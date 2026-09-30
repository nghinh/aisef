"""C2-P5 acceptance boundary: the real approvals are content-addressed, bound to the accepted proposal and given by the
established owner identity; a tampered or synthetic approval is refused; the acceptance re-derives on this tree."""

import copy
import json
import unittest

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


if __name__ == "__main__":
    unittest.main()
