"""WP-2.5.1 — the LedgerLock PLAN-V2.2 proposal (validation/qualification/p10_contracts.py).

P5-1 the 77 criteria are accounted for exactly once; P5-2 the migrated contracts compile and the plan admits with the
check approvals — and is refused without them (the approval gate holds: nothing is self-approved); P5-3 a test-named
criterion is refused by the kernel's contract rule (the six DECISION-3 befores, and a V2.2 entry naming a test);
P5-4 a universal criterion without declared quantifier semantics is refused, a DECISION-1 criterion declared
exhaustive is refused, a witness measurement on a FULL probe is refused; P5-5 DECISION-2/3/4 are carried as recorded;
P5-6 the committed record and document are what the aid derives from this tree.
"""

import copy
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load(name, rel):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


from aisef2.probe import process_effect as pe  # noqa: E402

A = _load("aisef_v2_p10_contracts", "validation/qualification/p10_contracts.py")
_BUILT = {}


def built():
    if not _BUILT:
        _BUILT.update(A.build())
    return _BUILT


def entry(ac):
    return next(e for e in built()["criteria"] if e["ac_id"] == ac)


class Coverage(unittest.TestCase):
    def test_P5_1_every_criterion_once(self):
        crit = built()["criteria"]
        self.assertEqual(len(crit), 77)
        self.assertEqual({e["ac_id"] for e in crit}, {r["ac_id"] for r in A.P10.v1_rows()})
        self.assertTrue(all(e["quantifier"] in A.QUANTIFIERS for e in crit))
        for e in crit:
            self.assertIsInstance(e["measured"], str)
            self.assertIsInstance(e["unmeasured"], list)


class Admission(unittest.TestCase):
    def test_P5_2_compiles_and_admits_only_with_the_check_approvals(self):
        b = built()
        compiled = [e for e in b["criteria"] if e["v22_status"] == "COMPILED"]
        self.assertEqual(len(b["plan"].obligations), len(compiled))
        self.assertGreater(len(compiled), 0)
        self.assertTrue(b["checked"].admitted, [c for c in b["checked"].checks if not c.passed])
        self.assertFalse(b["bare"].admitted)
        failed = {c.name for c in b["bare"].checks if not c.passed}
        self.assertEqual(failed, {"contract_spec_integrity", "traceability"})
        for e in compiled:
            self.assertTrue(e["probe_id"] != "probe.python_callable", "nothing new compiles against the Cycle-1 identity")

    def test_P5_2b_the_check_approver_is_not_the_owner(self):
        self.assertTrue(A.CHECK_APPROVER.startswith("human:"))
        self.assertNotIn("owner", A.CHECK_APPROVER)


class Refusals(unittest.TestCase):
    def _author(self, ac, t):
        r = next(x for x in A.P10.v1_rows() if x["ac_id"] == ac)
        return A.author(ac, t, r["requirement"], "MUST_HOLD", r["criterion"], A.requirements())

    def test_P5_3_test_named_criterion_refused(self):
        for ac in A.D3:
            before = {**A.P10.V2[ac], **A._meta(q=A.EX, measured="x")}
            with self.assertRaises(A.Refusal) as cm:
                self._author(ac, before)
            self.assertEqual(cm.exception.code, "REFUSED_BY_CONTRACT_RULE", ac)
        named = A.eff([A.NEW, A.call("verify")], {"returns": {"ok": True}}, locator="tests.test_ledger:Ledger", q=A.EX,
                      measured="x")
        with self.assertRaises(A.Refusal) as cm:
            self._author("AC-STORY-02-01-1", named)
        self.assertEqual(cm.exception.code, "REFUSED_BY_CONTRACT_RULE")
        self.assertEqual({entry(ac)["v22_status"] for ac in A.D3}, {"COMPILED", "REMOVED_FROM_PRODUCTPROOF"})

    def test_P5_4_quantifier_rules(self):
        t = copy.deepcopy(A.V22["AC-STORY-01-01-1"])
        del t["quantifier"]
        with self.assertRaises(A.Refusal) as cm:
            self._author("AC-STORY-01-01-1", t)
        self.assertEqual(cm.exception.code, "REFUSED_QUANTIFIER_UNDECLARED")
        t = {**A.V22["AC-STORY-04-03-1"], "quantifier": A.EX}
        with self.assertRaises(A.Refusal) as cm:
            self._author("AC-STORY-04-03-1", t)
        self.assertEqual(cm.exception.code, "REFUSED_UNIVERSAL_DECLARED_EXHAUSTIVE")
        t = {**A.V22["AC-STORY-01-01-4"], "quantifier": A.BW}
        with self.assertRaises(A.Refusal) as cm:
            self._author("AC-STORY-01-01-4", t)
        self.assertEqual(cm.exception.code, "REFUSED_WITNESS_UNDER_FULL")
        for ac in A.decision_criteria(1):
            self.assertIn(entry(ac)["quantifier"], (A.BW, A.UF), ac)


class Decisions(unittest.TestCase):
    def test_P5_5_decisions_as_recorded(self):
        for ac in A.decision_criteria(2):
            e = entry(ac)
            if e["v22_status"] == "COMPILED":
                faults = [s["fault"] for s in e["stimulus"]["scenario"] if s["step"] == "fault"]
                self.assertTrue(faults and all(f in pe.FAULTS for f in faults), ac)
            else:
                self.assertIn(e["v22_status"], ("UNSUPPORTED_STIMULUS", "UNSUPPORTED_OBSERVABLE"), ac)
        for ac in A.decision_criteria(4):
            self.assertIn("DECISION-4", entry(ac)["decisions"], ac)
        rec = A.record()
        self.assertEqual([m["ac_id"] for m in rec["decision_3_mappings"]], list(A.D3))
        self.assertFalse(any(m["approved"] for m in rec["decision_3_mappings"]))
        self.assertEqual(rec["approvals"]["given"], [])
        self.assertEqual(rec["problems"], [])


class Record(unittest.TestCase):
    def test_P5_6_committed_record_is_current(self):
        self.assertEqual(A.check(), [])


if __name__ == "__main__":
    unittest.main()
