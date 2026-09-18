"""SS-81 family — EXECUTION EVIDENCE VALIDITY (INV-TDD-NOP-PROOF, INV-T.EXECUTED-EVIDENCE).

The owner's twelve required regressions (decision "FIX SS-81 FAMILY", section 8) and every sibling from the section-7
sweep, each driven to its answer deterministically: no model, no network, no docker. Regression 2 runs the real
pinned pytest through the kernel's own collection strategy, parser and gate.
"""
from __future__ import annotations

import ast
import inspect
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aisef.control import gate, ledger as L, proof, tdd
from aisef.control.outcome import Outcome
from aisef.control.proof import Proof, classify, story_file_for
from aisef.harness.observe import EvidenceStore
from aisef.harness.testlog import parse
from aisef.harness.tools import collection_continuation_args

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "tests/fixtures/testlog"
SID = "S-01"
AC1, AC2 = "tests/test_a.py::test_AC_S_01_1_x", "tests/test_b.py::test_AC_S_01_2_y"
DEPS = "no runnable setup in this tree — the project's dependencies are not installed here"


def collection_error(file: str, module: str, name: str = "") -> dict:
    return {"file": file, "error": "import_name" if name else "module_not_found", "missing_module": module, "missing_name": name}


class GateCase(unittest.TestCase):
    """Story S-01 changes src/a.py; its criterion tests are green at candidate `aaa`."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = EvidenceStore(self._tmp.name)
        self.store.tool_run(SID, "test:baseline", ok=True, detail={
            "baseline": True, "test_format": "pytest", "test_ids": ["t1"], "failed_ids": [], "skipped_ids": []})

    def candidate(self, ids, **detail):
        s = EvidenceStore(self._tmp.name, candidate="aaa")
        s.file_change(SID, "src/a.py")
        s.tool_run(SID, "test", ok=True, detail={"test_format": "pytest", "test_ids": list(ids), "failed_ids": [], **detail})
        s.tool_run(SID, "lint", ok=True)
        s.tool_run(SID, "qa:fake-tests", ok=True, detail={"files": []})

    def nop(self, **detail):
        d = {"nop": True, "parent": "cha0000", "files": ["tests/test_a.py", "tests/test_b.py"], "test_format": "pytest",
             "test_ids": [], "failed_ids": [], "absent_at_parent": ["src/a.py"], **detail}
        EvidenceStore(self._tmp.name, candidate="aaa").tool_run(SID, "test:nop", ok=not d.get("failed_ids") and not d.get("unrunnable"), detail=d)

    def check(self, name="tests verify story", acceptance=2, **kw):
        g = gate.evaluate(SID, self.store.read(SID), changed=["src/a.py", "tests/test_a.py", "tests/test_b.py"],
                          write_scope=["src", "tests"], screens=[], review_blocking=[], candidate="aaa",
                          acceptance=acceptance, **kw)
        return next(c for c in g.checks if c.name == name)


# ----------------------------------------------------------------------------------------------- the twelve

class R01ThirdPartyMissingAtParent(GateCase):
    def test_a_third_party_dependency_missing_at_the_parent_is_unrunnable_never_pass(self):
        self.candidate([AC1])
        self.nop(unrunnable=DEPS, collection_errors=[collection_error("tests/test_a.py", "hypothesis")])
        m = self.check(acceptance=1)
        self.assertIs(m.outcome, Outcome.UNRUNNABLE, m.detail)
        self.assertIn("DEPENDENCY_UNRUNNABLE", m.detail)


class R02CollectionFailureDoesNotHideATautology(GateCase):
    """File A cannot import the story's new module at the parent (a legitimate red); file B holds a tautological AC
    test. With the kernel's collection strategy the real pytest keeps going, B is observed GREEN, the control FAILS."""

    def test_b_is_observed_green_and_the_control_fails(self):
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td)
            (proj / "tests").mkdir()
            (proj / "tests/test_a.py").write_text("from src.a import f\n\ndef test_AC_S_01_1_x():\n    assert f() == 1\n", encoding="utf-8")
            (proj / "tests/test_b.py").write_text("def test_AC_S_01_2_y():\n    assert True\n", encoding="utf-8")
            cmd = f"{sys.executable} -m pytest -v -p no:cacheprovider"
            args = collection_continuation_args(cmd)
            self.assertEqual(args, ["--continue-on-collection-errors"])
            r = subprocess.run([sys.executable, "-m", "pytest", "-v", "-p", "no:cacheprovider", *args], cwd=proj,
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            rec = parse(r.stdout + r.stderr).to_evidence()
        self.assertIn(AC2, rec["test_ids"], "the tautology ran although file A failed to collect")
        self.assertFalse(rec["collection_aborted"])
        self.candidate([AC1, AC2])
        self.nop(**{k: rec[k] for k in ("test_format", "test_ids", "failed_ids", "skipped_ids", "errored_ids",
                                        "collection_errors", "collection_aborted", "failure_imports", "output_complete")})
        m = self.check()
        self.assertIs(m.outcome, Outcome.FAILED, m.detail)
        self.assertIn(AC2, m.data["still_green"])
        self.assertEqual(m.data["proof"]["AC-S-01-1"]["tests"][AC1]["state"], "RED_COLLECTION_BOUND_TO_STORY")

    def test_without_the_strategy_the_same_run_proves_nothing(self):
        text = (FIX / "pytest-v-interrupted-collection-errors.txt").read_text(encoding="utf-8")
        rec = parse(text).to_evidence()
        st = classify(rec, ["tests/test_tautology.py::test_AC_STORY_01_02_4_tautology"], ["ledgerlock/store.py"])
        self.assertIs(st["tests/test_tautology.py::test_AC_STORY_01_02_4_tautology"][0], Proof.COLLECTION_ABORTED)


class R03StoryModuleBindsOnlyItsOwnFile(unittest.TestCase):
    def test_only_the_ac_whose_file_imports_the_missing_story_module_is_bound(self):
        rec = {"test_format": "pytest", "test_ids": [], "output_complete": True,
               "collection_errors": [collection_error("tests/test_a.py", "src.a")]}
        st = classify(rec, [AC1, AC2], ["src/a.py"], added=["src/a.py"])
        self.assertIs(st[AC1][0], Proof.RED_COLLECTION_BOUND_TO_STORY)
        self.assertIsNot(st[AC2][0], Proof.RED_COLLECTION_BOUND_TO_STORY, "file A's error proves nothing about file B")


class R04UnrelatedAcNotCollected(GateCase):
    def test_an_unrelated_ac_test_that_was_not_collected_gets_no_proof(self):
        self.candidate([AC1, AC2])
        self.nop(collection_errors=[collection_error("tests/test_a.py", "src.a"),
                                    {"file": "tests/test_b.py", "error": "syntax", "missing_module": "", "missing_name": ""}],
                 output_complete=True)
        m = self.check()
        self.assertIs(m.outcome, Outcome.UNRUNNABLE, m.detail)
        self.assertEqual(m.data["proof"]["AC-S-01-2"]["tests"][AC2]["state"], "NOT_COLLECTED")


class R05AllAcTestsFailAtParent(GateCase):
    def test_every_criterion_test_executed_red_passes(self):
        self.candidate([AC1, AC2])
        self.nop(test_ids=[AC1, AC2], failed_ids=[AC1, AC2], output_complete=True)
        m = self.check()
        self.assertIs(m.outcome, Outcome.PASSED, m.detail)
        self.assertTrue(all(a["proven"] for a in m.data["proof"].values()))


class R06OneGreenOthersRed(GateCase):
    def test_one_ac_green_at_the_parent_fails_the_control(self):
        self.candidate([AC1, AC2])
        self.nop(test_ids=[AC1, AC2], failed_ids=[AC1], output_complete=True)
        m = self.check()
        self.assertIs(m.outcome, Outcome.FAILED, m.detail)
        self.assertEqual(m.data["still_green"], [AC2])


class R07PackageRoot(unittest.TestCase):
    def test_a_missing_package_root_maps_to_its_init(self):                      # SS-82
        self.assertEqual(story_file_for("ledgerlock", ["ledgerlock/__init__.py", "ledgerlock/cli.py"]), "ledgerlock/__init__.py")
        self.assertEqual(story_file_for("ledgerlock.store", ["ledgerlock/store.py"]), "ledgerlock/store.py")
        self.assertEqual(story_file_for("app", ["src/app/__init__.py"]), "src/app/__init__.py")   # src/ layout

    def test_the_real_ss82_record_is_now_bound(self):
        """W1 T80 run 1, STORY-01-01: `No module named 'ledgerlock'` with the story adding ledgerlock/__init__.py."""
        rec = {"test_format": "pytest", "test_ids": [], "output_complete": True, "collection_aborted": True,
               "collection_errors": [collection_error("tests/test_nfc_normalization.py", "ledgerlock")]}
        t = "tests/test_nfc_normalization.py::test_AC_STORY_01_01_1_x"
        st = classify(rec, [t], ["ledgerlock/__init__.py", "ledgerlock/format.py"], added=["ledgerlock/__init__.py", "ledgerlock/format.py"])
        self.assertIs(st[t][0], Proof.RED_COLLECTION_BOUND_TO_STORY)


class R08ThirdPartyNeverMapsToStoryScope(unittest.TestCase):
    def test_a_third_party_name_is_anchored_at_import_roots(self):
        for missing, story in (("yaml", ["config/yaml.py"]), ("requests", ["requests_util.py"]),
                               ("hypothesis", ["tests_support/hypothesis.py"]), ("attr", ["src/models/attr.py"])):
            with self.subTest(missing=missing):
                self.assertEqual(story_file_for(missing, story), "")


class R09ToolEnvironmentFailure(GateCase):
    def test_a_tool_or_environment_failure_remains_unrunnable(self):
        self.candidate([AC1])
        self.nop(test_format="", unrunnable="tool not installed or cannot load (command not found) — set up the environment")
        self.assertIs(self.check(acceptance=1).outcome, Outcome.UNRUNNABLE)
        st = classify({"unrunnable": "tool not installed (exit 127)"}, [AC1], ["src/a.py"])
        self.assertIs(st[AC1][0], Proof.ENVIRONMENT_UNRUNNABLE)


class R10PartialOutputCannotPass(GateCase):
    def test_truncated_pytest_output_cannot_pass(self):
        full = (FIX / "pytest-v-continue-collection-errors.txt").read_text(encoding="utf-8")
        cut = parse(full[: full.index("=========================== short test summary")]).to_evidence()
        self.assertFalse(cut["output_complete"])
        self.candidate([AC1])
        self.nop(test_ids=[AC1], failed_ids=[AC1], output_complete=False)          # even an observed red
        m = self.check(acceptance=1)
        self.assertIs(m.outcome, Outcome.UNRUNNABLE, m.detail)
        self.assertIn("incomplete", m.detail)


class R11TestFormatDoesNotChangeTruth(GateCase):
    def test_the_same_evidence_with_and_without_test_format_gets_the_same_verdict(self):
        for errors, want in (([collection_error("tests/test_a.py", "hypothesis")], Outcome.UNRUNNABLE),
                             ([collection_error("tests/test_a.py", "src.a")], Outcome.PASSED)):
            got = []
            for fmt in ("pytest", ""):
                self.setUp()
                self.candidate([AC1])
                self.nop(test_format=fmt, unrunnable=DEPS, collection_errors=errors, output_complete=True)
                got.append(self.check(acceptance=1).outcome)
            with self.subTest(errors=errors[0]["missing_module"]):
                self.assertEqual(got, [want, want])


class R12OneProofModel(unittest.TestCase):
    """criteria / TDD / NOP / baseline / preservation / ledger all read test evidence through control/proof.py."""

    CONSUMERS = [(gate, "_nop_check"), (gate, "_baseline_check"), (gate, "_preservation_check"),
                 (tdd, "proven_red_before_green"), (tdd, "tdd_subjects"), (L, "_observe_tests")]

    def test_every_consumer_reads_evidence_through_the_proof_model(self):
        for mod, fn in self.CONSUMERS:
            src = inspect.getsource(getattr(mod, fn))
            with self.subTest(consumer=f"{mod.__name__}.{fn}"):
                self.assertTrue(any(k in src for k in ("proof.", "not_green(", "executed_green(")), "reads ids directly")

    def test_the_removed_any_red_rule_is_gone(self):
        tree = ast.parse(inspect.getsource(tdd))
        self.assertNotIn("red_before_green", {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)})

    def test_nop_and_tdd_agree_on_the_same_parent_record(self):
        rec = {"test_format": "pytest", "test_ids": [], "output_complete": True,
               "collection_errors": [collection_error("tests/test_a.py", "src.a")]}
        nop_red = all(p in proof.PROVES_RED for p, _ in classify(rec, [AC1], ["src/a.py"]).values())
        self.assertEqual(nop_red, proof.run_proves_red(rec, [AC1], ["src/a.py"]))


# ----------------------------------------------------------------------------------------------- siblings

class SS83TddRed(GateCase):
    def test_an_environment_failure_is_not_tdds_red(self):
        s = EvidenceStore(self._tmp.name, candidate="aaa")
        s.tool_run(SID, "test", ok=False, detail={"unrunnable": "tool not installed (exit 127)", "test_format": "", "test_ids": []})
        self.candidate([AC1])
        self.nop(test_ids=[AC1], failed_ids=[AC1], output_complete=True, files=["tests/test_a.py"])
        m = self.check("TDD", acceptance=1, added_tests=["tests/test_a.py"])
        self.assertIn("nop control", m.detail, "TDD may pass only through the proven nop, not the environment failure")

    def test_an_unrelated_red_is_not_tdds_red(self):
        s = EvidenceStore(self._tmp.name, candidate="aaa")
        s.tool_run(SID, "test", ok=False, detail={"test_format": "pytest", "test_ids": ["tests/test_old.py::t"],
                                                  "failed_ids": ["tests/test_old.py::t"]})
        self.candidate([AC1, "tests/test_old.py::t"])
        m = self.check("TDD", acceptance=1, added_tests=["tests/test_a.py"])
        self.assertIs(m.outcome, Outcome.FAILED, m.detail)


class SS84NoCriteria(GateCase):
    def test_a_red_parent_proves_nothing_for_a_story_without_criteria(self):
        self.candidate(["t1"])
        self.nop(test_format="", test_ids=[], failed_ids=["x"])
        self.assertIs(self.check(acceptance=0).outcome, Outcome.UNRUNNABLE)


class SS85BaselineNotExecuted(GateCase):
    def test_an_aborted_baseline_proves_no_regression_nothing(self):
        self.store.tool_run(SID, "test:baseline", ok=False, detail={
            "baseline": True, "test_format": "pytest", "test_ids": [], "failed_ids": [], "skipped_ids": [],
            "collection_aborted": True})
        self.candidate([AC1])
        self.assertIs(self.check("no baseline regression", acceptance=1).outcome, Outcome.UNRUNNABLE)


    def test_a_record_from_before_the_flag_is_read_from_its_tail(self):
        """Evidence written by the pre-fix harness has no `collection_aborted` field; the abort is in its tail."""
        self.store.tool_run(SID, "test:baseline", ok=False, detail={
            "baseline": True, "test_format": "pytest", "test_ids": [], "failed_ids": [], "skipped_ids": [],
            "tail": "ERROR tests/test_x.py\n!!!!!!!! Interrupted: 1 error during collection !!!!!!!!"})
        self.candidate([AC1])
        self.assertIs(self.check("no baseline regression", acceptance=1).outcome, Outcome.UNRUNNABLE)


class SS86BaselineSkipped(GateCase):
    def test_a_baseline_green_test_skipped_at_the_candidate_is_a_regression(self):
        self.candidate(["t1", AC1], skipped_ids=["t1"])
        m = self.check("no baseline regression", acceptance=1)
        self.assertIs(m.outcome, Outcome.FAILED, m.detail)
        self.assertIn("silenced", m.detail)


class SS87PreservationSkipped(GateCase):
    def test_a_verified_behaviour_whose_test_is_skipped_is_not_preserved(self):
        old = "tests/test_old.py::test_AC_S_00_1_old"
        self.candidate([old, AC1], skipped_ids=[old])
        m = self.check("preservation", acceptance=1, preservation=[{"id": "AC-S-00-1", "kind": "ac", "story": "S-00"}])
        self.assertIs(m.outcome, Outcome.UNRUNNABLE, m.detail)
        self.assertIn("not executed", m.detail)


class SS88LedgerSkipped(unittest.TestCase):
    def test_a_skipped_criterion_test_is_not_verified(self):
        led = L.Ledger()
        led.stories[SID] = L.StoryLine(id=SID, acceptance=1, covers=["FR-1"])

        class E:
            name, ok = "test", True
            detail = {"test_format": "pytest", "test_ids": [AC1], "failed_ids": [], "skipped_ids": [AC1]}
        L._observe_tests(led, E(), SID, 1, "aaa", 1.0)
        self.assertNotEqual(led.behaviors["AC-S-01-1"].status, L.VERIFIED)
        self.assertNotEqual(led.behaviors["FR-1"].status, L.VERIFIED)
        self.assertEqual(led.behaviors["AC-S-01-1"].source.get("why"), L.WHY_NOT_EXECUTED)


class SS89NoNopRecord(GateCase):
    def test_a_missing_control_blocks(self):
        self.candidate([AC1])
        m = self.check(acceptance=1)
        self.assertIs(m.outcome, Outcome.UNRUNNABLE)
        self.assertTrue(m.outcome.blocks)


# ------------------------------------------------------------ found by the section-9 historical re-audit (fix iteration)

class ReauditSymbolFromAChangedModule(GateCase):
    """w1-run-1 STORY-01-02, measured: `cannot import name 'GENESIS' from 'ledgerlock.format'` — the story changes
    ledgerlock/format.py, which exists at the parent. The first fix bound nothing here: level 1 of the nop check
    rebound the name `changed` to its renamed-tests list, so level 2 saw no story files whenever level 1 ran (it runs
    in this fixture: the baseline carries names and no distinct branch point)."""

    def test_a_symbol_the_story_adds_to_an_existing_module_is_bound(self):
        self.candidate([AC1, AC2])
        self.nop(absent_at_parent=[], test_ids=[AC2], failed_ids=[AC2],
                 collection_errors=[collection_error("tests/test_a.py", "src.a", "GENESIS")])
        m = self.check()
        self.assertIs(m.outcome, Outcome.PASSED, m.detail)
        self.assertEqual(m.data["proof"]["AC-S-01-1"]["tests"][AC1]["state"], "RED_COLLECTION_BOUND_TO_STORY")


class ReauditSubmoduleTheStoryAdds(GateCase):
    """w1-run-1 STORY-01-04, measured: `from ledgerlock import store` → `cannot import name 'store' from 'ledgerlock'`,
    ledgerlock/store.py added by the story."""

    def test_a_submodule_the_story_adds_is_bound(self):
        self.candidate([AC1, AC2])
        self.nop(test_ids=[AC2], failed_ids=[AC2], collection_errors=[collection_error("tests/test_a.py", "src", "a")])
        m = self.check()
        self.assertIs(m.outcome, Outcome.PASSED, m.detail)

    def test_another_file_under_the_package_is_package_matching_not_proof(self):
        err = collection_error("tests/test_a.py", "src", "x")
        st = classify({"test_format": "pytest", "test_ids": [], "collection_errors": [err]}, [AC1], ["src/other.py"], added=[])
        self.assertIs(st[AC1][0], Proof.DEPENDENCY_UNRUNNABLE)
        self.assertEqual(story_file_for("src", ["src/other.py"], package_dir=False), "")
        self.assertEqual(proof.bound(err, ["src/other.py"], ["src/other.py"]), (False, ""))


if __name__ == "__main__":
    unittest.main()
