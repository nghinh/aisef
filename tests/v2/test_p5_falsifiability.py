"""WP-2.5.2 — SpecFalsifiabilityEvidence for the PLAN-V2.2 proposal specs over the LedgerLock reference fixture
(validation/qualification/p5_falsifiability.py; RFC §9.1.2).

P5F-1 a proposal spec the reference satisfies refutes its designed mutant, and the evidence passes the frozen
`falsifiability_problems`; P5F-2 a spec the reference does not satisfy is reported REFERENCE_NOT_SATISFIED with the
reference's observation, and no mutant is run against it; P5F-3 a designed mutant the spec cannot refute is reported in
`unrefuted_designed`, never hidden; P5F-5 C2-P5-FINDING-001 reproduced; P5F-4 the committed record accounts for every criterion of the proposal, binds the
proposal it measured, and every QUALIFIED row carries only valid evidence. Real subjects, real probes, the catalog.
"""

import importlib.util
import json
import pathlib
import sys
import tempfile
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


F = _load("aisef_v2_p5_falsifiability", "validation/qualification/p5_falsifiability.py")
_BUILT = {}


def built():
    if not _BUILT:
        _BUILT.update(F._aid().build())
    return _BUILT


def row(ac):
    return next(e for e in built()["criteria"] if e["ac_id"] == ac)


def targets():
    return {m["id"]: m["target"] for m in F._trees()._p0()._catalog()}


class Falsifiability(unittest.TestCase):
    def _run(self, ac, mutants):
        e = row(ac)
        spec = built()["specs"][e["spec_id"]]
        with tempfile.TemporaryDirectory(prefix="aisef-p5f-", ignore_cleanup_errors=True) as tmp:
            work = pathlib.Path(tmp)
            trees = {"reference": F._trees().build_tree(None, work)}
            trees.update({m: F._trees().build_tree(m, work) for m in mutants})
            return F.falsify(e, spec, trees, {m: t for m, t in targets().items() if m in mutants})

    def test_P5F_1_a_satisfied_spec_refutes_its_designed_mutant(self):
        out = self._run("AC-STORY-03-01-1", ["M-3.2-1"])
        self.assertEqual(out["reference"], "SATISFIED")
        self.assertEqual(out["status"], "QUALIFIED")
        self.assertEqual(out["refuted"], ["M-3.2-1"])
        self.assertTrue(all(not ev["falsifiability_problems"] for ev in out["evidence"]))

    def test_P5F_2_a_spec_the_reference_does_not_satisfy_is_reported_and_no_mutant_runs(self):
        out = self._run("AC-STORY-01-01-2", ["M-3.1-1"])
        self.assertEqual(out["status"], "REFERENCE_NOT_SATISFIED")
        self.assertEqual(out["verdicts"], {})
        self.assertEqual(out["reference_observation"]["kind"], "SUBJECT_ABSENT")
        self.assertEqual(out["unrefuted_designed"], ["M-3.1-1"])

    def test_P5F_3_an_unrefuted_designed_mutant_is_reported(self):
        out = self._run("AC-STORY-02-01-3", ["M-3.3-1"])
        self.assertEqual(out["reference"], "SATISFIED")
        self.assertEqual(out["refuted"], [])
        self.assertEqual(out["unrefuted_designed"], ["M-3.3-1"])
        self.assertEqual(out["status"], "NOT_QUALIFIED")

    def test_P5F_5_finding_001_the_inverted_prohibitions_fail_a_correct_reference(self):
        with tempfile.TemporaryDirectory(prefix="aisef-p5f-", ignore_cleanup_errors=True) as tmp:
            out = F.reproduce_finding_001(built(), F._trees().build_tree(None, pathlib.Path(tmp)))
        self.assertTrue(out["reproduced"])
        for ac, r in out["specs"].items():
            self.assertEqual((r["polarity"], r["expectation"], r["reference"]), ("MUST_NOT_HOLD", "REFUTED", "SATISFIED"), ac)


class Record(unittest.TestCase):
    def test_P5F_4_the_record_accounts_for_the_proposal(self):
        rec = json.loads((ROOT / F.OUT_REL).read_text(encoding="utf-8"))
        proposal = json.loads((ROOT / F._aid().OUT_REL).read_text(encoding="utf-8"))
        self.assertEqual(rec["identities"]["proposal_digest"], proposal["proposal_digest"])
        self.assertEqual(rec["identities"]["plan_hash"], proposal["plan"]["plan_hash"])
        self.assertEqual({r["ac_id"] for r in rec["specs"]}, {e["ac_id"] for e in proposal["criteria"]})
        compiled = {e["ac_id"]: e["spec_id"] for e in proposal["criteria"] if e["v22_status"] == "COMPILED"}
        for r in rec["specs"]:
            if r["ac_id"] in compiled:
                self.assertEqual(r["spec_id"], compiled[r["ac_id"]])
                self.assertIn(r["status"], ("QUALIFIED", "NOT_QUALIFIED", "REFERENCE_NOT_SATISFIED"))
            else:
                self.assertEqual(r["status"], "NO_SPEC")
            if r["status"] == "QUALIFIED":
                self.assertEqual(r["reference"], "SATISFIED")
                self.assertTrue(r["refuted"])
                self.assertTrue(all(not ev["falsifiability_problems"] for ev in r["evidence"]))
        self.assertEqual(rec["problems"], [])


if __name__ == "__main__":
    unittest.main()
