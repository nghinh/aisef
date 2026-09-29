"""WP-2.3.2 — the `process_effect` probe's calibration and its specs' falsifiability (RFC §9.1, §9.1.1, §9.1.2).

PECAL-1 the three classes calibrated by the frozen `calibrate()` over the committed small fixtures, with contrast, and
rejected once the fixtures stop contrasting; PECAL-2 the LedgerLock calibration builder's trees are the frozen blobs,
and a materialised mutant is the reference plus exactly its declared change; PECAL-3 an authored spec is SATISFIED on
the reference and REFUTES its mutant (a fast subset; the full matrix is the evidence run,
validation/qualification/c2_effect_calibration.py --run); PECAL-4 a spec that no mutant refutes is reported NOT
QUALIFIED by the builder. Real subjects, real probe, the catalog registry.
"""

import difflib
import importlib.util
import json
import pathlib
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict  # noqa: E402
from aisef2.probe import catalog, process_effect as pe  # noqa: E402
from aisef2.probe.calibration import (  # noqa: E402
    NotQualified, SpecFalsifiabilityEvidence, calibrate, calibration_env, falsifiability_problems,
)


def _load(name, rel):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


B = _load("aisef_v2_c2_effect_calibration", "validation/qualification/c2_effect_calibration.py")
P0 = B._p0()
FIX = ROOT / "tests/v2/fixtures/calibration/process_effect"
QUANTIFIERS = ("exhaustive_finite_domain", "bounded_witness_measurement", "unsupported_for_full_enforcement")


def snapshot(root: pathlib.Path) -> dict:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()
            and "__pycache__" not in p.parts}


def _calibrate(cls, pos, neg):
    return calibrate(pe.ProcessEffectProbe(), cls, pos, neg, calibration_env(sys.executable), time.time,
                     registry=catalog.registry())


class _Trees(unittest.TestCase):
    def work(self) -> pathlib.Path:
        d = tempfile.TemporaryDirectory(prefix="aisef2-pecal-", ignore_cleanup_errors=True)
        self.addCleanup(d.cleanup)
        return pathlib.Path(d.name)

    def trees(self, *mutants):
        work = self.work()
        return {"reference": B.build_tree(None, work), **{m: B.build_tree(m, work) for m in mutants}}


class Calibration(_Trees):
    def test_PECAL_1_the_three_classes_calibrated_with_contrast_over_the_small_fixtures(self):
        for cls in pe.CLASSES:
            pos, neg = FIX / cls / "positive", FIX / cls / "negative"
            with self.subTest(cls=cls):
                rec = _calibrate(cls, pos, neg)
                self.assertEqual((rec.probe_id, rec.probe_digest, rec.observation_class), (pe.PROBE_ID, pe.DIGEST, cls))
                for a, b in ((neg, neg), (pos, pos)):   # the same fixtures reject the probe once they stop contrasting
                    with self.assertRaises(NotQualified):
                        _calibrate(cls, a, b)
                self.assertEqual((pos / "request.json").read_bytes(), (neg / "request.json").read_bytes())
                src = [(side / "checkout" / "tally.py").read_text(encoding="utf-8").split("\n") for side in (pos, neg)]
                changed = [d for d in difflib.ndiff(*src) if d[:1] in "+-"]
                self.assertEqual(len(changed), 2, changed)   # the negative is a one-line mutant of the positive
        # a fixture pair of another class is not a calibration of this one
        with self.assertRaises(NotQualified) as refused:
            _calibrate("scenario_files", FIX / "scenario_returns" / "positive", FIX / "scenario_returns" / "negative")
        self.assertIn("asks for 'scenario_returns', not 'scenario_files'", str(refused.exception))

    def test_PECAL_2_the_ledgerlock_trees_are_the_frozen_blobs_and_a_mutant_is_the_reference_plus_its_change(self):
        frozen = snapshot(ROOT / B.FIX_REL)
        work = self.work()
        ref = B.build_tree(None, work)
        committed = {p.relative_to(P0.REF): p.read_bytes() for p in P0.REF.rglob("*") if p.is_file()}
        self.assertEqual({p.relative_to(ref): p.read_bytes() for p in ref.rglob("*") if p.is_file()}, committed)
        for m in P0._catalog():
            tree = B.build_tree(m["id"], work)
            for module in P0.MODULES:
                with self.subTest(mutant=m["id"], module=module):
                    got = (tree / "ledgerlock" / module).read_text(encoding="utf-8")
                    reference = (P0.REF / "ledgerlock" / module).read_text(encoding="utf-8")
                    if module not in P0.modules_of(m):
                        self.assertEqual(got, reference)
                        continue
                    self.assertEqual(got, P0._expected_module(m, module))
                    self.assertEqual(got.encode("utf-8"), (P0.MUT / m["id"] / module).read_bytes().replace(b"\r\n", b"\n"))
                    changes = [c for c in P0.changes_of(m) if c["module"] == module]
                    diff = [d for d in difflib.ndiff(reference.split("\n"), got.split("\n")) if d[:1] in "+-"]
                    self.assertTrue(diff)
                    self.assertLessEqual(sum(1 for d in diff if d.startswith("-")), len(changes))
        # a materialised module that differs from the committed blob is refused, never used
        with mock.patch.object(P0, "_expected_module", lambda m, module: "tampered\n"), self.assertRaises(SystemExit):
            B.build_tree("M-6-1", work / "again")
        # each LedgerLock class negative is a mutant whose declared target the class's request observes
        for cls, row in B.LEDGERLOCK_CLASSES.items():
            self.assertIn(B._mutant(row["mutant"])["target"], B.spec_def(row["spec"])["requirements"], cls)
        # nothing under the frozen fixture was written, nothing added, nothing removed
        self.assertEqual(snapshot(ROOT / B.FIX_REL), frozen)

    def test_PECAL_3_an_authored_spec_is_satisfied_on_the_reference_and_refutes_its_mutant(self):
        trees = self.trees("M-4.3-1", "M-6-1", "M-8-1")
        row = B.falsifiability(B.spec_def("LL-CONFLICT-1"), trees)
        self.assertEqual((row["reference"], row["refuted"], row["status"], row["problems"]),
                         ("SATISFIED", ["M-4.3-1"], "QUALIFIED", []))
        self.assertEqual((row["designed_for"], row["unrefuted_designed"]), (["M-4.3-1"], []))
        self.assertEqual(row["verdicts"], {"M-4.3-1": "REFUTED", "M-6-1": "SATISFIED", "M-8-1": "SATISFIED"})
        [ev] = row["evidence"]
        self.assertEqual((ev["mechanism"], ev["counterexample_ref"], ev["observed"], ev["falsifiability_problems"]),
                         ("controlled_product_mutation", f"{B.FIX_REL}/mutants/M-4.3-1", "REFUTED", []))
        contract, spec = B.compile_contract(B.spec_def("LL-CONFLICT-1"))
        self.assertEqual((row["spec_id"], row["semantic_hash"], spec.probe_id, spec.probe_digest),
                         (spec.id, spec.semantic_hash, pe.PROBE_ID, pe.DIGEST))
        self.assertEqual(catalog.registry().observation_class(pe.PROBE_ID, pe.DIGEST, spec), "scenario_raises")
        # the evidence object is validated, both ways: a SATISFIED observation does not qualify a SATISFIED expectation
        ok = SpecFalsifiabilityEvidence(spec.id, spec.semantic_hash, "controlled_product_mutation", "M-4.3-1",
                                        BehaviorVerdict.REFUTED)
        self.assertEqual(falsifiability_problems(ok, spec), [])
        self.assertTrue(falsifiability_problems(SpecFalsifiabilityEvidence(
            spec.id, spec.semantic_hash, "controlled_product_mutation", "M-6-1", BehaviorVerdict.SATISFIED), spec))
        # the DECISION-2 fault step: an append whose fsync fails must not return; the mutant without the fsync does
        row = B.falsifiability(B.spec_def("LL-FSYNC-2"), trees)
        self.assertEqual((row["reference"], row["refuted"], row["quantifier_semantics"]),
                         ("SATISFIED", ["M-8-1"], "bounded_witness_measurement"))
        # the class calibrations over the reference: each negative is its class's mutant
        records, problems = B.ledgerlock_calibrations(self.work())
        self.assertEqual(problems, [])
        self.assertEqual({r["observation_class"]: r["mutant"] for r in records},
                         {cls: row["mutant"] for cls, row in B.LEDGERLOCK_CLASSES.items()})
        self.assertTrue(all(r["non_contrasting_pair_rejected"] and r["probe_digest"] == pe.DIGEST for r in records))

    def test_PECAL_4_a_spec_that_no_mutant_refutes_is_reported_NOT_QUALIFIED(self):
        always = {"id": "LL-ALWAYS-1", "family": "hash chain", "requirements": ["R-3.2"],
                  "claim": "an append ends the file with a newline", "locator": B.LEDGER,
                  "scenario": [B.NEW, B.put("a", 1, "r1", 1)], "observable": {"files": {B.L: {"final_byte": "\n"}}},
                  "quantifier": "exhaustive_finite_domain"}
        row = B.falsifiability(always, self.trees("M-3.2-1", "M-3.2-2", "M-6-1"))
        self.assertEqual((row["reference"], row["refuted"], row["status"], row["qualified"], row["evidence"]),
                         ("SATISFIED", [], "NOT QUALIFIED", False, []))
        self.assertEqual(row["unrefuted_designed"], ["M-3.2-1", "M-3.2-2"])
        with mock.patch.object(B, "SPECS", [always]):
            table = B.falsifiability_table(self.work())
        self.assertEqual((table["qualified"], table["not_qualified"]), ([], ["LL-ALWAYS-1"]))
        self.assertEqual(table["gap_mutants_refuted_by_no_spec"], [m["id"] for m in P0._catalog()])
        self.assertEqual(table["requirement_sections_covered"], [])

    def test_the_authored_specs_are_closed_over_the_requirements_map(self):
        rmap = json.loads((ROOT / B.FIX_REL / "REQUIREMENTS-MAP.json").read_text(encoding="utf-8"))
        kinds = {r["id"]: r["kind"] for r in rmap["requirements"]}
        self.assertEqual(len({d["id"] for d in B.SPECS}), len(B.SPECS))
        self.assertGreaterEqual(len({d["family"] for d in B.SPECS}), 6)
        for d in B.SPECS:
            with self.subTest(spec=d["id"]):
                self.assertTrue(set(d["requirements"]) <= {k for k, v in kinds.items() if v in ("BEHAVIOUR", "STATIC")})
                self.assertIn(d["quantifier"], QUANTIFIERS)
                if any(s["step"] == "fault" for s in d["scenario"]):
                    self.assertEqual(d["quantifier"], "bounded_witness_measurement")   # DECISION-1
                _, spec = B.compile_contract(d)
                self.assertIsNotNone(pe.spec_class(spec))
        self.assertEqual(B.H, B.chain_hashes({"op": "put", "key": "a", "value": 1, "ts": 1, "id": "r1"},
                                             {"op": "put", "key": "b", "value": 2, "ts": 2, "id": "r2"}))
        self.assertEqual(B.H[0], __import__("hashlib").sha256(
            b'GENESIS|{"hash":"","id":"r1","key":"a","op":"put","prev_hash":"","ts":1,"value":1}').hexdigest())


if __name__ == "__main__":
    unittest.main()
