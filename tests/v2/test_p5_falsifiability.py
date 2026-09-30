"""WP-2.5.2 (corrected) — SpecFalsifiabilityEvidence per retained PLAN-V2.2 spec with its own P5 witness
(validation/qualification/p5_falsifiability.py; RFC §9.1.2).

P5F-1 the P5 corpus is content-addressed: every witness reproduces its sealed digests, one witness per spec, and the
frozen reference is untouched; P5F-2 a retained spec is satisfied by the pristine reference and refuted by its own
witness, the evidence passing the frozen `falsifiability_problems` (one spec per probe kind); P5F-3 a witness a spec
cannot refute is classified NOT_QUALIFIED, never hidden; P5F-5 C2-P5-FINDING-001 stays reproducible; P5F-4 the committed
record: every retained spec QUALIFIED, none NOT_QUALIFIED, none unsatisfied by the reference, none without a witness.
"""

import hashlib
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
_SPECS = {}


def spec(sid):
    if not _SPECS:
        _SPECS.update(F._aid().build()["compiled"])
    return _SPECS[sid]


def witness(sid):
    return next(m for m in F.corpus()["mutants"] if m["spec"] == sid)


class Falsifiability(unittest.TestCase):
    def test_P5F_1_the_corpus_is_content_addressed_and_the_reference_untouched(self):
        self.assertEqual(F.corpus_problems(), [])
        fixture = json.loads((ROOT / "closure-evidence/v2/cycle2/P0-REFERENCE-FIXTURE.json").read_text(encoding="utf-8"))["fixture"]
        for name, text in F.reference_modules().items():
            self.assertEqual(hashlib.sha256(text.encode("utf-8")).hexdigest(), fixture[f"reference/ledgerlock/{name}"]["sha256"], name)

    def _pair(self, sid, mutant):
        with tempfile.TemporaryDirectory(prefix="aisef-p5f-", ignore_cleanup_errors=True) as tmp:
            work = pathlib.Path(tmp)
            ref, mut = F.build_tree(None, work), F.build_tree(mutant, work)
            return F.verdict_of(F.observe(spec(sid), ref)), F.verdict_of(F.observe(spec(sid), mut))

    def test_P5F_2_a_retained_spec_is_satisfied_and_refutes_its_own_witness(self):
        for sid in ("S-3.3-c", "S-9-b", "S-13-d", "S-12-c"):
            with self.subTest(spec=sid):
                pristine, refuted = self._pair(sid, witness(sid))
                self.assertEqual(F.classify(spec(sid).candidate_expectation.value, pristine, refuted), "QUALIFIED")
                self.assertEqual(F.evidence(spec(sid), witness(sid)["id"], refuted)["falsifiability_problems"], [])

    def test_P5F_3_a_witness_the_spec_cannot_refute_is_not_qualified(self):
        pristine, other = self._pair("S-9-b", witness("S-3.1-a"))
        self.assertEqual(F.classify(spec("S-9-b").candidate_expectation.value, pristine, other), "NOT_QUALIFIED")

    def test_P5F_5_finding_001_is_reproduced(self):
        with tempfile.TemporaryDirectory(prefix="aisef-p5f-", ignore_cleanup_errors=True) as tmp:
            out = F.reproduce_finding_001(F.build_tree(None, pathlib.Path(tmp)))
        self.assertTrue(out["reproduced"])
        self.assertEqual((out["expectation"], out["reference"]), ("REFUTED", "SATISFIED"))


class Record(unittest.TestCase):
    def test_P5F_4_every_retained_spec_is_qualified(self):
        rec = json.loads((ROOT / F.OUT_REL).read_text(encoding="utf-8"))
        proposal = json.loads((ROOT / F._aid().OUT_REL).read_text(encoding="utf-8"))
        self.assertEqual(rec["identities"]["proposal_digest"], proposal["proposal_digest"])
        s = rec["summary"]
        self.assertEqual((s["qualified"], s["not_qualified"], s["reference_not_satisfied"], s["specs_without_witness"]),
                         (s["retained_specs"], 0, 0, 0))
        self.assertEqual({r["spec_id"] for r in rec["specs"]}, {x["spec_id"] for x in proposal["specs"]})
        for r in rec["specs"]:
            self.assertEqual((r["status"], r["pristine"]), ("QUALIFIED", "SATISFIED" if r["expectation"] == "SATISFIED" else "REFUTED"))
            self.assertEqual(r["evidence"]["falsifiability_problems"], [], r["spec_id"])
        self.assertTrue(rec["finding_001"]["reproduced"])
        self.assertEqual(rec["problems"], [])


if __name__ == "__main__":
    unittest.main()
