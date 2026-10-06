"""WP-2.5.2 (corrected) — SpecFalsifiabilityEvidence per retained PLAN-V2.2 spec with its own P5 witness
(validation/qualification/p5_falsifiability.py; RFC §9.1.2).

P5F-1 the P5 corpus is content-addressed: every witness reproduces its sealed digests, one witness per spec, and the
frozen reference is untouched; P5F-2 a retained spec is satisfied by the pristine reference and refuted by its own
witness, the evidence passing the frozen `falsifiability_problems` (one spec per probe kind); P5F-3 a witness a spec
cannot refute is classified NOT_QUALIFIED, never hidden; P5F-5 C2-P5-FINDING-001 stays reproducible; P5F-4 the committed
record: every retained spec QUALIFIED, none NOT_QUALIFIED, none unsatisfied by the reference, none without a witness;
P5F-4b (owner B-03a) the v2.1 record is the same measurement on 2.1, naming the v2.1 proposal and the B-03a decision; P5F-6
the writers: the v2.1 record is run() under its own header, written once and never from an uncommitted kernel, a
refused run kept outside the evidence tree; the 2.0 record and the sealed corpus are never rewritten.
"""

import copy
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

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

    def test_P5F_4b_the_v2_1_record_measures_the_v2_1_proposal(self):
        from validation.qualification import p5_acceptance as PA
        rec = json.loads((ROOT / F.V21_OUT_REL).read_text(encoding="utf-8"))
        proposal = PA.v21_proposal_record()
        self.assertEqual({k: rec[k] for k in F.v21_header()}, F.v21_header())
        self.assertEqual(rec["identities"]["proposal"], PA._file(PA.V21_PROPOSAL_REL))
        self.assertEqual((rec["identities"]["proposal_digest"], rec["identities"]["plan_hash"]),
                         (proposal["proposal_digest"], proposal["plan"]["plan_hash"]))
        s = rec["summary"]
        self.assertEqual((s["qualified"], s["not_qualified"], s["reference_not_satisfied"], s["specs_without_witness"]),
                         (s["retained_specs"], 0, 0, 0))
        self.assertEqual({r["spec_id"] for r in rec["specs"]}, {x["spec_id"] for x in proposal["specs"]})
        self.assertEqual(rec["problems"], [])


def _git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, encoding="utf-8", check=True).stdout.strip()


class Writers(unittest.TestCase):
    """P5F-6: never the real tree — ROOT is a temporary directory; git still reads this repository."""
    RUN = {"record": "2.0 title", "authority": "owner ruling 2026-09-30", "status": "MEASUREMENT", "supersedes": {"commit": "0f77995"},
           "identities": {"plan_hash": "p", "proposal": {"path": F.OUT_REL, "sha256": "o"}, "proposal_digest": "856e"},
           "specs": [], "problems": [], "verdict": "COMPLETE — EVERY RETAINED SPEC QUALIFIED", "summary": {}, "elapsed_s": 1.0}
    PROPOSAL = {"plan": {"plan_hash": "p"}, "proposal_digest": "46a5"}
    FILE = {"path": "closure-evidence/v2/v2.1/P5-PLAN-V2.2-PROPOSAL.json", "sha256": "f" * 64}

    def setUp(self):
        from validation.qualification import p5_acceptance as PA
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        for patch in (mock.patch.object(F, "ROOT", self.root), mock.patch.object(F, "_git", side_effect=_git),
                      mock.patch.object(PA, "_file", return_value=self.FILE), mock.patch.object(F, "_plan_hash", return_value="p")):
            patch.start()
            self.addCleanup(patch.stop)
        git = mock.patch.object(PA, "_git", return_value="")     # the kernel committed: git status mocked, never the real tree's
        self.pa_git = git.start()
        self.addCleanup(git.stop)
        self.PA = PA

    def proposal(self, rec):
        return mock.patch.object(self.PA, "v21_proposal_record", return_value=rec)

    def test_the_v2_1_record_is_run_under_its_own_header_naming_the_v2_1_proposal(self):
        with self.proposal(self.PROPOSAL):
            out = F.as_v21(copy.deepcopy(self.RUN))
        self.assertEqual(out["authority"], self.PA.B03_REF)
        self.assertIsNone(out["supersedes"])
        self.assertNotIn("NOT approved", out["status"])
        self.assertEqual(out["history"], {"path": F.OUT_REL, "blob_at_v2_0_0": _git("rev-parse", f"{self.PA.V2_0_0}:{F.OUT_REL}")})
        self.assertEqual(out["identities"], {"plan_hash": "p", "proposal": self.FILE, "proposal_digest": "46a5",
                                             "probe_execution_digests": {}})
        from aisef2.probe import catalog
        from aisef2.probe.calibration import executing
        active = {e.probe_id: e.probe_digest for e in catalog.CATALOG if e.active}
        with self.proposal(self.PROPOSAL):          # the bytes each spec's probe runs (V2-007), one entry per probe
            ran = F.as_v21({**copy.deepcopy(self.RUN), "specs": [{"probe_id": p} for p in [*active, *active][:len(active) + 1]]})
        digests = ran["identities"]["probe_execution_digests"]
        self.assertEqual(digests, {p: executing(F._probe(p)) for p in active})
        self.assertEqual(len(set(digests.values())), len(active))
        for p, capability in active.items():         # not the capability digest a spec binds
            self.assertNotEqual(digests[p], capability, p)
        self.assertEqual({k: v for k, v in out.items() if k not in F.v21_header() and k != "identities"},
                         {k: v for k, v in self.RUN.items() if k not in F.v21_header() and k != "identities"})
        for prop in ({}, {"plan": {"plan_hash": "q"}, "proposal_digest": "46a5"}):   # missing, or another plan's proposal
            with self.subTest(prop=prop), self.proposal(prop), self.assertRaises(SystemExit):
                F.as_v21(copy.deepcopy(self.RUN))

    def test_the_v2_1_writer_writes_once_and_only_a_clean_run_of_the_v2_1_proposal(self):
        path = self.root / F.V21_OUT_REL
        with self.proposal({}), mock.patch.object(F, "run", side_effect=AssertionError("run")), self.assertRaises(SystemExit):
            F.write_v21()                                     # no v2.1 proposal: refused before the run
        with self.proposal({**self.PROPOSAL, "plan": {"plan_hash": "q"}}), mock.patch.object(F, "run", side_effect=AssertionError("run")), \
                self.assertRaises(SystemExit) as refused:
            F.write_v21()                                     # a v2.1 proposal of another plan than this tree's: before the run
        self.assertIn("another plan than this tree's", str(refused.exception))
        with tempfile.TemporaryDirectory() as kept:
            kept = pathlib.Path(kept).resolve()
            for name, ran, why in (("a problem", {**self.RUN, "problems": ["x"]}, "x"),
                                   ("another plan", {**self.RUN, "identities": {**self.RUN["identities"], "plan_hash": "q"}},
                                    "its plan is not the run's")):
                before = set(kept.iterdir())
                with self.subTest(name), self.proposal(self.PROPOSAL), mock.patch.object(F, "run", return_value=copy.deepcopy(ran)), \
                        mock.patch.dict(os.environ, {"AISEF_FAILED_RUN_DIR": str(kept)}), self.assertRaises(SystemExit) as refused:
                    F.write_v21()                             # a refused run is never written as evidence, and kept
                self.assertFalse(path.exists())
                (newest,) = set(kept.iterdir()) - before
                self.assertIn(f"— the run is kept at {newest}", str(refused.exception))
                self.assertIn(why, str(refused.exception))
                doc = json.loads(newest.read_text(encoding="utf-8"))
                self.assertEqual(doc["specs"], ran["specs"])
                self.assertIn(why, "; ".join(doc["problems"]))
            self.assertEqual(len(list(kept.iterdir())), 2)
        self.assertEqual(list(self.root.rglob("*")), [])
        with self.proposal(self.PROPOSAL), mock.patch.object(F, "run", return_value=copy.deepcopy(self.RUN)):
            rec = F.write_v21()
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), rec)
        self.assertEqual(rec["authority"], self.PA.B03_REF)
        with self.proposal(self.PROPOSAL), mock.patch.object(F, "run", side_effect=AssertionError("run")), self.assertRaises(SystemExit):
            F.write_v21()                                     # an existing record: refused before the run
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), rec)

    def test_the_v2_1_writer_refuses_an_uncommitted_kernel_before_it_runs(self):
        dirty = " M aisef2/product/outcome.py"
        self.pa_git.return_value = dirty
        with self.proposal(self.PROPOSAL), mock.patch.object(F, "run", side_effect=AssertionError("run")), \
                self.assertRaises(SystemExit) as refused:
            F.write_v21()
        self.pa_git.assert_called_once_with("status", "--porcelain", "--", "aisef2")
        self.assertEqual(str(refused.exception), f"refused: aisef2 has uncommitted changes {[dirty]} — a v2.1 record binds HEAD:aisef2")
        self.assertEqual(list(self.root.rglob("*")), [])
        self.pa_git.return_value = ""                    # committed: the writer goes on to the run
        with self.proposal(self.PROPOSAL), mock.patch.object(F, "run", side_effect=AssertionError("run")), self.assertRaises(AssertionError):
            F.write_v21()

    def test_the_sealed_corpus_is_never_rewritten(self):
        ref = f"{F.FIX_REL}/reference/ledgerlock"
        shutil.copytree(ROOT / ref, self.root / ref)
        sealed = (ROOT / F.MUTANTS_REL).read_bytes()
        target = self.root / F.MUTANTS_REL
        target.parent.mkdir(parents=True)
        target.write_bytes(sealed)
        with mock.patch("sys.stdout"):
            self.assertEqual(F.main(["--seal"]), 0)           # the seal it already is: nothing to write
        self.assertEqual(target.read_bytes(), sealed)
        doc = json.loads(sealed)
        doc["corpus_sha256"] = "0" * 64                        # a corpus this seal would change
        changed = (json.dumps(doc, indent=1, ensure_ascii=False) + "\n").encode("utf-8")
        target.write_bytes(changed)
        with self.assertRaises(SystemExit) as refused:
            F.main(["--seal"])
        self.assertIn(f"{F.MUTANTS_REL} is a sealed C2-P5 input", str(refused.exception))
        self.assertEqual(target.read_bytes(), changed)

    def test_the_2_0_record_is_never_rewritten(self):
        (self.root / F.OUT_REL).parent.mkdir(parents=True)
        (self.root / F.OUT_REL).write_text("2.0", encoding="utf-8")
        with mock.patch.object(F, "run", side_effect=AssertionError("run")), self.assertRaises(SystemExit):
            F.main(["--run"])
        self.assertEqual((self.root / F.OUT_REL).read_text(encoding="utf-8"), "2.0")


if __name__ == "__main__":
    unittest.main()
