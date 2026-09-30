"""WP-2.5.1 (corrected) — the requirements-grounded LedgerLock PLAN-V2.2 proposal (validation/qualification/p10_contracts.py).

P5-1 the 77 PLAN-V2.1 criteria each carry exactly one of the four classes, a normative one maps to specs and no other
class does; P5-2 every retained spec compiles and the plan admits with the synthetic approvals — and is refused without
any (the approval gate holds; nothing is approved); P5-3 a test-named subject is refused by the kernel's contract rule;
P5-4 the DECISION-1 rules (undeclared quantifier, a DECISION-1 spec declared exhaustive, a witness under FULL) refuse;
P5-4b C2-P5-FINDING-001: a prohibition written as its permitted condition under MUST_NOT_HOLD is refused; P5-5 the
coverage matrix: every spec traces to a normative clause, every normative clause is covered, every other clause carries
its reason, R-11 stays engineering-test; P5-6 no spec rests on a PLAN-V2.1-only surface; P5-7 one witness per spec in the
P5 corpus; P5-8 the committed record and document are current.
"""

import importlib.util
import json
import pathlib
import re
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


A = _load("aisef_v2_p10_contracts", "validation/qualification/p10_contracts.py")
_BUILT = {}


def built():
    if not _BUILT:
        _BUILT.update(A.build())
    return _BUILT


class Classification(unittest.TestCase):
    def test_P5_1_every_criterion_has_one_class(self):
        self.assertEqual(set(A.CRITERIA), {r["ac_id"] for r in A.P10.v1_rows()})
        for ac, c in A.CRITERIA.items():
            self.assertIn(c["class"], A.CLASSES, ac)
            self.assertEqual(bool(c["specs"]), c["class"] == A.N, ac)
            self.assertTrue(set(c["specs"]) <= set(A.SPECS), ac)
        for ac in ("AC-STORY-05-01-3", "AC-STORY-05-02-1", "AC-STORY-05-02-2", "AC-STORY-05-02-3"):
            self.assertEqual(A.CRITERIA[ac]["class"], A.E, ac)


class Admission(unittest.TestCase):
    def test_P5_2_compiles_and_admits_only_with_the_synthetic_approvals(self):
        b = built()
        self.assertEqual({s["status"] for s in b["specs"]}, {"COMPILED"})
        self.assertTrue(b["checked"].admitted, [c for c in b["checked"].checks if not c.passed])
        self.assertFalse(b["bare"].admitted)
        self.assertEqual({c.name for c in b["bare"].checks if not c.passed}, {"contract_spec_integrity", "traceability"})
        self.assertNotIn("probe.python_callable", {s["probe_id"] for s in b["specs"]})

    def test_P5_2b_the_synthetic_identity_is_not_an_approval(self):
        self.assertTrue(A.SYNTHETIC_APPROVER.startswith("human:"))
        self.assertIn("NOT-AN-APPROVAL", A.SYNTHETIC_APPROVER)
        self.assertNotIn("owner", A.SYNTHETIC_APPROVER.lower())


class Refusals(unittest.TestCase):
    def _author(self, sid, entry):
        return A.author(sid, entry, A.requirements())

    def test_P5_3_a_test_named_subject_is_refused(self):
        for ac in A.D3:
            before = {**A.P10.V2[ac], "requirement": "R-3.3", "quantifier": A.EX, "measured": "x"}
            with self.assertRaises(A.Refusal) as cm:
                self._author(ac, before)
            self.assertEqual(cm.exception.code, "REFUSED_BY_CONTRACT_RULE", ac)

    def test_P5_4_quantifier_rules(self):
        t = {k: v for k, v in A.SPECS["S-3.1-a"].items() if k != "quantifier"}
        with self.assertRaises(A.Refusal) as cm:
            self._author("S-3.1-a", t)
        self.assertEqual(cm.exception.code, "REFUSED_QUANTIFIER_UNDECLARED")
        with self.assertRaises(A.Refusal) as cm:
            self._author("S-3.1-a", {**A.SPECS["S-3.1-a"], "quantifier": A.EX})
        self.assertEqual(cm.exception.code, "REFUSED_UNIVERSAL_DECLARED_EXHAUSTIVE")
        with self.assertRaises(A.Refusal) as cm:
            self._author("S-12-a", {**A.SPECS["S-12-a"], "quantifier": A.BW})
        self.assertEqual(cm.exception.code, "REFUSED_WITNESS_UNDER_FULL")

    def test_P5_4b_finding_001_a_prohibition_written_as_its_permitted_condition_is_refused(self):
        inverted = {**A.INVERTED_FORM, "requirement": "R-12", "quantifier": A.EX, "polarity": "MUST_NOT_HOLD", "measured": "x"}
        with self.assertRaises(A.Refusal) as cm:
            self._author("FINDING-001", inverted)
        self.assertEqual(cm.exception.code, "REFUSED_POLARITY_INVERTED")
        self.assertEqual(A.SPECS["S-3.4-a"]["polarity"], "MUST_NOT_HOLD")
        self.assertEqual(A.SPECS["S-3.4-a"]["states"], "forbidden")
        for sid in ("S-12-a", "S-12-b", "S-12-c", "S-10-a"):
            self.assertEqual(A.SPECS[sid].get("polarity", "MUST_HOLD"), "MUST_HOLD", sid)


class Coverage(unittest.TestCase):
    def test_P5_5_the_coverage_matrix(self):
        clauses = {c["id"]: c for c in A.CLAUSES}
        for sid, s in A.SPECS.items():
            self.assertEqual(clauses[s["clause"]]["class"], A.N, sid)
            self.assertIn(sid, {x for c in A.CLAUSES for x in c["specs"]}, sid)
        for c in A.CLAUSES:
            if c["class"] == A.N:
                self.assertTrue(c["specs"], c["id"])
            if c["class"] in (A.U, A.E):
                self.assertTrue(c.get("reason"), c["id"])
        self.assertEqual(clauses["R-11/1"]["class"], A.E)

    def test_P5_6_no_spec_rests_on_a_plan_only_surface(self):
        for sid, s in A.SPECS.items():
            self.assertFalse(re.search(r"ledgerlock\.(format|store)\b", s["locator"]), sid)
            for step in s["stimulus"].get("scenario", []):
                if step["step"] in ("call", "expect_raises", "construct"):
                    self.assertIn(step.get("method", "<construct>"), ("apply_batch", "snapshot", "verify", "<construct>"), sid)
            obs = json.dumps(s["observable"])
            self.assertNotIn('"stdout"', obs.replace('"streams": ["stdout"]', ""), sid)
            self.assertNotIn('"stderr"', obs, sid)
            self.assertNotIn('"field": "hash"', obs, sid)
            self.assertNotIn('"field": "prev_hash"', obs, sid)
            self.assertNotIn('"sha256"', obs, sid)

    def test_P5_7_one_witness_per_spec(self):
        corpus = json.loads((ROOT / A.MUTANTS_REL).read_text(encoding="utf-8"))["mutants"]
        self.assertEqual(sorted(m["spec"] for m in corpus), sorted(A.SPECS))


class Record(unittest.TestCase):
    def test_P5_8_committed_record_is_current(self):
        # current up to the authoring-kernel provenance, the one field an authorized later kernel changes (owner, 2026-10-01)
        from validation.qualification import p5_acceptance as PA
        found = A.check()
        if PA.current_proposal_currency()["provenance_only"]:
            found = [p for p in found if p != f"{A.OUT_REL} is not what the authoring aid derives from this tree"]
        self.assertEqual(found, [])
        rec = json.loads((ROOT / A.OUT_REL).read_text(encoding="utf-8"))
        self.assertEqual(rec["approvals"]["given"], [])
        self.assertFalse(any(m["approved"] for m in rec["decision_3_mappings"]))


if __name__ == "__main__":
    unittest.main()
