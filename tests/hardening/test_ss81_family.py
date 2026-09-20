"""SS-81 family — EXECUTION EVIDENCE VALIDITY (INV-TDD-NOP-PROOF, INV-T.EXECUTED-EVIDENCE).

The owner's twelve required regressions (decision "FIX SS-81 FAMILY", section 8) and every sibling from the section-7
sweep, each driven to its answer deterministically: no model, no network, no docker. Regression 2 runs the real
pinned pytest through the kernel's own collection strategy, parser and gate.
"""
from __future__ import annotations

import ast
import importlib.util
import inspect
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aisef.control import gate, ledger as L, proof, tdd
from tests import obligations  # noqa: E402
from aisef.control.outcome import Outcome
from aisef.control.proof import Proof, classify, story_file_for
from aisef.harness.observe import NOTE, Event, Evidence, EvidenceStore
from aisef.harness.testlog import MAX_IDS, missing_import, parse
from aisef.harness.tools import NO_MANIFEST, NO_SETUP, collection_continuation_args

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
        kw.setdefault("ac_proof", obligations(SID, acceptance))    # V1's question, declared as V1's obligation
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

    @unittest.skipUnless(importlib.util.find_spec("pytest"), "needs pytest to run; the twin below reads its committed real output")
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
        self.assertIn("AC-S-01-2", m.data["still_green"])      # V2 names the criterion
        self.assertIn(AC2, [t for r in m.data["rows"] for t in r["tests"]])
        self.assertEqual(m.data["proof"]["AC-S-01-1"]["tests"][AC1]["state"], "RED_COLLECTION_BOUND_TO_STORY")

    def test_the_committed_real_output_with_the_strategy_shows_the_tautology_green(self):
        """The real pytest 9.1.1 run with --continue-on-collection-errors (tests/fixtures/testlog), read by the kernel's
        parser: other files' import errors do not hide the tautology, and it is observed GREEN."""
        rec = parse((FIX / "pytest-v-continue-collection-errors.txt").read_text(encoding="utf-8")).to_evidence()
        taut = "tests/test_tautology.py::test_AC_STORY_01_02_4_tautology"
        self.assertFalse(rec["collection_aborted"])
        self.assertIs(classify(rec, [taut], ["ledgerlock/store.py"])[taut][0], Proof.GREEN_EXECUTED)

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
        self.assertEqual(m.data["still_green"], ["AC-S-01-2"])
        self.assertEqual([r["tests"] for r in m.data["rows"] if r["ac_id"] == "AC-S-01-2"], [[AC2]])


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


# ------------------------------------------------------ Phase 13 on F7: each surviving mutant of 2026-09-18, killed
# (closure-evidence/hardening/mutation-results.json at e60cba2 — 104 survivors; the parsers' real-output fixtures had
# never been asserted, and several decision branches had no test of their own)

UT = (FIX / "unittest-v-import-errors.txt").read_text(encoding="utf-8")
NODE = (FIX / "node-test-missing-module.txt").read_text(encoding="utf-8")
PYC = (FIX / "pytest-v-continue-collection-errors.txt").read_text(encoding="utf-8")


class KillUnittestParsing(unittest.TestCase):
    def test_each_module_that_cannot_import_is_one_collection_error_and_the_run_is_complete(self):
        rec = parse(UT).to_evidence()
        self.assertEqual([(e["file"], e["module"], e["error"], e["missing_module"], e["missing_name"]) for e in rec["collection_errors"]],
                         [("tests/test_story_module.py", "tests.test_story_module", "module_not_found", "ledgerlock.store", ""),
                          ("tests/test_story_symbol.py", "tests.test_story_symbol", "import_name", "ledgerlock", "normalize_key"),
                          ("tests/test_third_party.py", "tests.test_third_party", "module_not_found", "hypothesis", "")])
        self.assertIs(rec["output_complete"], True)

    def test_the_last_error_block_is_read_even_when_the_text_ends_inside_it(self):
        # routed to unittest only by a `Ran` line: here an earlier run's, so the cut run's last block ends the text
        cut = UT[: UT.index("\n----------------------------------------------------------------------\nRan ")]
        rec = parse("Ran 0 tests in 0.000s\n\nOK\n" + cut).to_evidence()
        self.assertEqual([e["missing_module"] for e in rec["collection_errors"]], ["ledgerlock.store", "ledgerlock", "hypothesis"])
        self.assertFalse(parse(cut).to_evidence()["test_format"], "no summary at all: not read as a run")

    def test_a_ran_count_that_disagrees_with_the_names_read_is_incomplete(self):
        self.assertIs(parse(UT.replace("Ran 3 tests", "Ran 4 tests")).to_evidence()["output_complete"], False)

    def test_a_test_failing_on_an_import_inside_its_body_names_what_is_missing_and_an_assertion_does_not(self):
        text = ("test_a (tests.test_a.T.test_a) ... ERROR\ntest_b (tests.test_a.T.test_b) ... FAIL\n\n"
                "======================================================================\nERROR: test_a (tests.test_a.T.test_a)\n"
                "----------------------------------------------------------------------\nTraceback (most recent call last):\n"
                "  File \"/w/tests/test_a.py\", line 5, in test_a\n    import yaml\nModuleNotFoundError: No module named 'yaml'\n\n"
                "======================================================================\nFAIL: test_b (tests.test_a.T)\n"
                "----------------------------------------------------------------------\nTraceback (most recent call last):\n"
                "AssertionError: 1 != 2\n\n----------------------------------------------------------------------\n"
                "Ran 2 tests in 0.001s\n\nFAILED (failures=1, errors=1)\n")
        rec = parse(text).to_evidence()
        self.assertEqual(rec["failure_imports"], {"tests.test_a.T.test_a": {"missing_module": "yaml", "missing_name": ""}})
        self.assertEqual(rec["collection_errors"], [])


class KillNodeParsing(unittest.TestCase):
    def test_the_real_node_output_names_the_file_and_the_target_relative_to_the_project(self):
        rec = parse(NODE).to_evidence()
        self.assertEqual(rec["collection_errors"], [{"file": "tests/a.test.js", "module": "", "error": "module_not_found",
                                                     "missing_module": "src/add.js", "missing_name": "", "importer": "tests/a.test.js"}])

    def test_duplicates_collapse_distinct_targets_and_files_do_not_and_packages_stay_bare(self):
        text = ("Error [ERR_MODULE_NOT_FOUND]: Cannot find module '/workspace/src/add.js' imported from /workspace/tests/a.test.jsx\n" * 2
                + "Error [ERR_MODULE_NOT_FOUND]: Cannot find module '/workspace/src/sub.js' imported from /workspace/tests/a.test.jsx\n"
                "Error [ERR_MODULE_NOT_FOUND]: Cannot find module '/workspace/src/add.js' imported from /workspace/tests/b.test.js\n"
                "Error [ERR_PACKAGE_NOT_FOUND]: Cannot find package 'express' imported from /workspace/tests/c.test.js\n"
                "✖ tests/a.test.jsx (7ms)\n✖ tests/b.test.js (7ms)\n✖ tests/c.test.js (7ms)\n✔ AC_S_01_2 tautology (0.7ms)\n"
                "ℹ tests 4\nℹ pass 1\nℹ fail 3\n")
        got = [(e["file"], e["missing_module"]) for e in parse(text).to_evidence()["collection_errors"]]
        self.assertEqual(got, [("tests/a.test.jsx", "src/add.js"), ("tests/a.test.jsx", "src/sub.js"),
                               ("tests/b.test.js", "src/add.js"), ("tests/c.test.js", "express")])

    def test_a_node_criterion_file_that_cannot_load_is_bound_and_the_tautology_beside_it_is_green(self):
        rec = parse(NODE).to_evidence()
        red, taut = "AC_STORY_01_02_1 adds two numbers", "AC_STORY_01_02_2 tautology"
        files = proof.files_of([red, taut], "STORY-01-02", 2, {"AC-STORY-01-02-1": ["tests/a.test.js"],
                                                               "AC-STORY-01-02-2": ["tests/b.test.js"]})
        self.assertEqual(files, {red: ["tests/a.test.js"], taut: ["tests/b.test.js"]})
        st = classify(rec, [red, taut], ["src/add.js"], added=["src/add.js"], files=files)
        self.assertIs(st[red][0], Proof.RED_COLLECTION_BOUND_TO_STORY)
        self.assertIs(st[taut][0], Proof.GREEN_EXECUTED)

    def test_files_of_reads_a_pytest_id_from_the_id_and_a_title_from_the_scan(self):
        self.assertEqual(proof.files_of([AC1, "AC_S_01_2 title"], SID, 2, {"AC-S-01-2": ["tests/b.test.js"]}),
                         {AC1: ["tests/test_a.py"], "AC_S_01_2 title": ["tests/b.test.js"]})
        self.assertEqual(proof.files_of([AC1], SID, 1, None), {AC1: ["tests/test_a.py"]})
        self.assertEqual(proof.files_of(["AC_S_01_2 title"], SID, 0, {"AC-S-01-2": ["tests/b.test.js"]}), {"AC_S_01_2 title": []})


class KillCollectionContinuationArgs(unittest.TestCase):
    def test_only_pytest_in_program_position_gets_the_flag(self):
        gate_flag = "--continue-on-collection-errors"
        flag = [gate_flag]
        for cmd in ("pytest -v", "py.test", "python -m pytest -q", "python3.12 -m pytest", "/usr/bin/python3 -m pytest",
                    "uv run pytest -x", "poetry run python -m pytest", "pdm run pytest", "pytest.exe -v"):
            self.assertEqual(collection_continuation_args(cmd), flag, cmd)
        for cmd in (f"python -m pytest {gate_flag}", "tox -e pytest", "make pytest", "npm run pytest", "npm test", "python -m unittest",
                    "python -m", "python pytest", "sh -c 'pytest -q'", "uv run", "", "echo 'unbalanced"):
            self.assertEqual(collection_continuation_args(cmd), [], cmd)


class KillPytestParsing(unittest.TestCase):
    def test_the_real_continue_run_is_complete_with_its_errored_and_import_failures(self):
        rec = parse(PYC).to_evidence()
        self.assertIs(rec["output_complete"], True)
        self.assertEqual(rec["errored_ids"], ["tests/test_setup_error.py::test_AC_STORY_01_02_8_uses_fixture"])
        self.assertEqual(rec["failure_imports"], {
            "tests/test_setup_error.py::test_AC_STORY_01_02_8_uses_fixture": {"missing_module": "ledgerlock.store", "missing_name": ""},
            "tests/test_tautology.py::test_AC_STORY_01_02_6_dep_in_body": {"missing_module": "yaml", "missing_name": ""}})

    def test_without_its_summary_line_the_run_is_incomplete(self):
        self.assertIs(parse("\n".join(PYC.splitlines()[:-1])).to_evidence()["output_complete"], False)

    def test_xpass_is_green_and_no_tests_ran_is_a_complete_empty_run(self):
        rec = parse("tests/t.py::test_x XPASS\ntests/t.py::test_y PASSED\n===== 1 passed, 1 xpassed in 0.01s =====\n").to_evidence()
        self.assertEqual(sorted(proof.executed_green(rec)), ["tests/t.py::test_x", "tests/t.py::test_y"])
        self.assertIs(rec["output_complete"], True)
        empty = parse("===== test session starts =====\ncollected 0 items\n\n===== no tests ran in 0.01s =====\n").to_evidence()
        self.assertEqual((empty["test_format"], empty["test_ids"], empty["output_complete"]), ("pytest", [], True))

    def test_an_error_block_at_the_very_end_of_a_cut_output_is_still_read(self):
        text = ("===== test session starts =====\ntests/test_b.py::test_y PASSED\n===== ERRORS =====\n"
                "_____ ERROR collecting tests/test_a.py _____\nE   ModuleNotFoundError: No module named 'x'\n")
        rec = parse(text).to_evidence()
        self.assertEqual([(e["file"], e["missing_module"]) for e in rec["collection_errors"]], [("tests/test_a.py", "x")])
        self.assertIs(rec["output_complete"], False)

    def test_missing_import_names_a_syntax_error_and_nothing_for_an_assertion(self):
        self.assertEqual(missing_import("E     SyntaxError: invalid syntax")["error"], "syntax")
        self.assertEqual(missing_import("E     AssertionError: 1 != 2"), {"error": "", "missing_module": "", "missing_name": ""})


class KillClassifyBranches(unittest.TestCase):
    RUN = {"test_format": "pytest", "output_complete": True}

    def test_an_import_failure_inside_a_failed_or_errored_test_binds_only_to_the_storys_module(self):
        t1, t2 = "tests/test_a.py::test_AC_S_01_1_x", "tests/test_a.py::test_AC_S_01_1_y"
        imp = {"missing_module": "src.a", "missing_name": "f"}
        d = {**self.RUN, "test_ids": [t1, t2], "failed_ids": [t1], "errored_ids": [t2], "failure_imports": {t1: imp, t2: imp}}
        st = classify(d, [t1, t2], ["src/a.py"])
        self.assertEqual((st[t1][0], st[t2][0]), (Proof.RED_EXECUTED, Proof.RED_COLLECTION_BOUND_TO_STORY))
        d["failure_imports"] = {t1: {"missing_module": "yaml", "missing_name": ""}}
        self.assertIs(classify(d, [t1], ["src/a.py"])[t1][0], Proof.DEPENDENCY_UNRUNNABLE)

    def test_only_a_missing_manifest_the_story_itself_adds_is_proof(self):
        t = AC1
        self.assertIs(classify({"unrunnable": NO_MANIFEST}, [t], [], added=["pyproject.toml"])[t][0], Proof.RED_COLLECTION_BOUND_TO_STORY)
        self.assertIs(classify({"unrunnable": NO_MANIFEST}, [t], [], added=[])[t][0], Proof.ENVIRONMENT_UNRUNNABLE)
        self.assertIs(classify({"unrunnable": NO_MANIFEST}, [t], ["pyproject.toml"], added=None)[t][0], Proof.ENVIRONMENT_UNRUNNABLE)
        self.assertIs(classify({"unrunnable": DEPS}, [t], [], added=["pyproject.toml"])[t][0], Proof.DEPENDENCY_UNRUNNABLE)
        self.assertIs(classify({"unrunnable": "docker daemon not reachable"}, [t], [])[t][0], Proof.ENVIRONMENT_UNRUNNABLE)

    def test_the_reason_names_what_the_file_could_not_import(self):
        d = {**self.RUN, "test_ids": [], "collection_errors": [collection_error("tests/test_a.py", "src.a", "GENESIS"),
                                                                collection_error("tests/test_b.py", "src.b"),
                                                                {"file": "tests/test_c.py", "error": "syntax", "missing_module": "", "missing_name": ""}]}
        t3 = "tests/test_c.py::test_AC_S_01_3_z"
        st = classify(d, [AC1, AC2, t3], ["src/a.py", "src/b.py"], added=["src/b.py"])
        self.assertIn("`GENESIS` from src.a", st[AC1][1])
        self.assertIn("cannot import src.b —", st[AC2][1])
        self.assertIn("failed to collect (syntax)", st[t3][1])

    def test_unreadable_or_incomplete_output_is_malformed_and_a_complete_run_without_the_test_is_absent(self):
        self.assertIs(classify({"test_format": "pytest", "test_ids": [], "output_complete": False}, [AC1], [])[AC1][0], Proof.MALFORMED_EVIDENCE)
        st = classify({"test_ids": []}, [AC1], [])
        self.assertEqual(st[AC1], (Proof.MALFORMED_EVIDENCE, "the runner's output cannot be read completely"))
        self.assertEqual(classify({"test_ids": [], "test_note": "no names"}, [AC1], [])[AC1][1], "no names")
        self.assertIs(classify({**self.RUN, "test_ids": []}, [AC1], [])[AC1][0], Proof.ABSENT)

    def test_a_criterion_is_proven_only_when_every_one_of_its_tests_is(self):
        t2 = "tests/test_a.py::test_AC_S_01_1_y"
        per = proof.summarize({AC1: (Proof.RED_EXECUTED, ""), t2: (Proof.ABSENT, "")}, SID, 1)
        self.assertIs(per["AC-S-01-1"]["proven"], False)

    def test_bound_takes_only_import_errors_and_resolves_js_through_the_importer(self):
        self.assertEqual(proof.bound({"error": "syntax", "missing_module": "x"}, ["x.py"], ["x.py"]), (False, ""))
        self.assertEqual(proof.bound({"error": "module_not_found", "missing_module": "../src/add.js", "importer": "tests/a.test.js"},
                                     ["src/add.js"], ["src/add.js"]), (True, "src/add.js"))
        self.assertEqual(story_file_for("src/add.js", ["src/add.js"], importer="tests/a.test.js"), "src/add.js")
        self.assertEqual(story_file_for("./src/add.js", ["src/add.js"]), "", "a relative target without its importer resolves to nothing")


class NoBaselineCase(GateCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = EvidenceStore(self._tmp.name)


class KillNopWithoutABaseline(NoBaselineCase):
    def test_level_two_decides_alone_when_no_baseline_was_recorded(self):
        self.candidate([AC1])
        self.nop(test_ids=[AC1], failed_ids=[AC1], output_complete=True)
        self.assertIs(self.check(acceptance=1).outcome, Outcome.PASSED)


class KillNopLevelOne(NoBaselineCase):
    def baseline(self, **detail):
        self.store.tool_run(SID, "test:baseline", ok=True, detail={"baseline": True, "test_format": "pytest", "skipped_ids": [],
                                                                  "failed_ids": [], **detail})

    def test_a_rerun_baseline_cannot_compare_and_says_so(self):
        self.baseline(test_ids=[AC1], parent="p1", base_ref="b0")
        self.candidate([AC1])
        self.nop(test_ids=[AC1], failed_ids=[AC1], output_complete=True)
        m = self.check(acceptance=1)
        self.assertIs(m.outcome, Outcome.PASSED, m.detail)
        self.assertIn("level 1 cannot compare", m.detail)

    def test_at_the_branch_point_a_criterion_test_green_before_the_story_is_tagging(self):
        self.baseline(test_ids=[AC1], parent="b0", base_ref="b0")
        self.candidate([AC1])
        self.nop(test_ids=[AC1], failed_ids=[AC1], output_complete=True)
        self.assertIs(self.check(acceptance=1).outcome, Outcome.FAILED)

    def test_a_criterion_test_red_or_skipped_at_the_baseline_was_not_green_before(self):
        for key in ("failed_ids", "skipped_ids"):
            with self.subTest(key=key):
                self.setUp()
                self.baseline(**{"test_ids": [AC1], key: [AC1]})
                self.candidate([AC1])
                self.nop(test_ids=[AC1], failed_ids=[AC1], output_complete=True)
                self.assertIs(self.check(acceptance=1).outcome, Outcome.PASSED)

    def test_a_branch_point_baseline_of_an_earlier_contract_epoch_is_not_compared(self):
        self.baseline(test_ids=[AC1], parent="b0", base_ref="b0", epoch="e1")
        self.store.record(SID, Event(kind=NOTE, name="story:contract", detail={"fingerprint": "e2"}))
        self.candidate([AC1])
        self.nop(test_ids=[AC1], failed_ids=[AC1], output_complete=True)
        m = self.check(acceptance=1)
        self.assertIs(m.outcome, Outcome.PASSED, m.detail)
        self.assertNotIn("tagged", m.detail)

    def test_a_truncated_baseline_list_is_unrunnable(self):
        self.baseline(test_ids=[f"tests/t.py::test_{i}" for i in range(MAX_IDS)])
        self.candidate([AC1])
        self.nop(test_ids=[AC1], failed_ids=[AC1], output_complete=True)
        self.assertIs(self.check(acceptance=1).outcome, Outcome.UNRUNNABLE)


class KillNopMessagesAndData(GateCase):
    def test_counts_strategy_and_the_ellipsis_are_reported(self):
        t3 = "tests/test_a.py::test_AC_S_01_1_z"
        self.candidate([AC1, AC2, t3])
        self.nop(test_ids=[AC2, t3], failed_ids=[AC2, t3], output_complete=True, collection_strategy="--continue-on-collection-errors",
                 collection_errors=[{"file": "tests/test_a.py", "error": "module_not_found", "missing_module": "src.a", "missing_name": ""}])
        m = self.check()
        self.assertIs(m.outcome, Outcome.PASSED, m.detail)
        self.assertIn("2 executed red, 1 unable to import", m.detail)
        self.assertEqual(m.data["strategy"], "--continue-on-collection-errors")

    def test_the_executed_red_count_is_counted(self):
        self.candidate([AC1, AC2])
        self.nop(test_ids=[AC2], failed_ids=[AC2], output_complete=True,
                 collection_errors=[{"file": "tests/test_a.py", "error": "module_not_found", "missing_module": "src.a", "missing_name": ""}])
        self.assertIn("1 executed red, 1 unable to import", self.check().detail)

    def test_more_than_three_unproven_tests_end_in_an_ellipsis(self):
        ids = [f"tests/test_a.py::test_AC_S_01_{i}_x" for i in range(1, 5)]
        self.candidate(ids)
        self.nop(output_complete=True)
        self.assertTrue(self.check(acceptance=4).detail.endswith("…"))
        self.setUp()
        self.candidate(ids[:3])
        self.nop(output_complete=True)
        self.assertFalse(self.check(acceptance=3).detail.endswith("…"))

    def test_a_green_parent_run_without_names_names_the_story_files(self):
        s = EvidenceStore(self._tmp.name, candidate="aaa")
        s.tool_run(SID, "test", ok=True, detail={})
        EvidenceStore(self._tmp.name, candidate="aaa").tool_run(SID, "test:nop", ok=True, detail={
            "nop": True, "parent": "cha0000", "files": ["tests/test_a.py"]})
        m = self.check(acceptance=1)
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("tests/test_a.py", m.detail)


class BaselineCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = EvidenceStore(self._tmp.name)

    def run_(self, base: dict, cand: dict | None = None, flaky: list | None = None):
        self.store.tool_run(SID, "test:baseline", ok=not base.get("unrunnable"), detail={"baseline": True, **base})
        if cand is not None:
            EvidenceStore(self._tmp.name, candidate="aaa").tool_run(SID, "test", ok=not cand.get("failed_ids"), detail=cand)
        if flaky:
            self.store.record(SID, Event(kind=NOTE, name=gate.REPEAT_NOTE, detail={"flaky_ids": flaky}))
        return gate._baseline_check(self.store.read(SID), "aaa")


class KillBaselineBranches(BaselineCase):
    def test_nothing_to_regress_names_what_the_baseline_lacked(self):
        self.assertIn("had no project", self.run_({"unrunnable": NO_MANIFEST}).detail)
        self.setUp()
        m = self.run_({"unrunnable": f"{NO_SETUP} — x", "test_files_in_tree": 0})
        self.assertIs(m.outcome, Outcome.NOT_APPLICABLE)
        self.assertIn("had no test file", m.detail)

    def test_unreadable_names_carry_the_runners_own_note(self):
        self.assertEqual(self.run_({"test_note": "base note"}).detail, "base note")
        self.setUp()
        self.assertIn("cannot read test names from baseline", self.run_({}).detail)
        self.setUp()
        self.assertEqual(self.run_({"test_format": "pytest", "test_ids": ["t"]}, {"test_note": "cand note"}).detail, "cand note")

    def test_a_candidate_run_that_did_not_execute_is_unrunnable(self):
        m = self.run_({"test_format": "pytest", "test_ids": ["t"]}, {"unrunnable": "tool missing"})
        self.assertIs(m.outcome, Outcome.UNRUNNABLE)

    def test_a_truncated_list_on_either_side_is_unrunnable(self):
        many = [f"tests/t.py::test_{i}" for i in range(MAX_IDS)]
        m = self.run_({"test_format": "pytest", "test_ids": many[:2]}, {"test_format": "pytest", "test_ids": many})
        self.assertIs(m.outcome, Outcome.UNRUNNABLE)
        self.setUp()
        m = self.run_({"test_format": "pytest", "test_ids": many}, {"test_format": "pytest", "test_ids": many[:1]})
        self.assertIs(m.outcome, Outcome.UNRUNNABLE)

    def test_a_flaky_test_is_not_counted_and_is_stated(self):
        m = self.run_({"test_format": "pytest", "test_ids": ["t", "u"]}, {"test_format": "pytest", "test_ids": ["t", "u"], "failed_ids": ["u"]},
                      flaky=["u"])
        self.assertIs(m.outcome, Outcome.PASSED)
        self.assertIn("flaky", m.detail)


class KillPreservationBranches(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def check(self, items, candidate="aaa", qa=None, mockup=None):
        s = EvidenceStore(self._tmp.name, candidate=candidate)
        s.tool_run(SID, "test", ok=True, detail={"test_format": "pytest", "test_ids": ["t"], "failed_ids": []})
        for name, (ok, detail) in (qa or {}).items():
            s.tool_run(SID, name, ok=ok, detail=detail)
        for name, detail in (mockup or {}).items():
            s.record(SID, Event(kind="mockup_map", name=name, ok=not detail.get("unavailable"), detail=detail))
        return gate._preservation_check(EvidenceStore(self._tmp.name).read(SID), items, candidate)

    def test_a_skipped_check_or_an_uncompared_screen_or_an_unknown_kind_is_unverified(self):
        for items, qa, mockup in (([{"id": "qa:e2e", "kind": "qa"}], {"qa:e2e": (False, {"skipped": "not configured"})}, None),
                                  ([{"id": "mockup:home", "kind": "mockup"}], None, {"home": {"unavailable": True}}),
                                  ([{"id": "X-1", "kind": "other"}], None, None)):
            with self.subTest(items=items):
                self.setUp()
                self.assertIs(self.check(items, qa=qa, mockup=mockup).outcome, Outcome.UNRUNNABLE)

    def test_a_red_check_is_a_regression(self):
        self.assertIs(self.check([{"id": "qa:e2e", "kind": "qa"}], qa={"qa:e2e": (False, {})}).outcome, Outcome.FAILED)

    def test_the_reasons_name_the_candidate_and_end_in_an_ellipsis_beyond_three(self):
        items = [{"id": f"X-{i}", "kind": "other"} for i in range(4)]
        m = self.check(items)
        self.assertIn("at candidate aaa:", m.detail)
        self.assertIn("…", m.detail)
        self.setUp()
        self.assertNotIn("…", self.check(items[:3], candidate="").detail)
        self.setUp()
        self.assertIn("at candidate this:", self.check(items[:1], candidate="").detail)
        self.setUp()
        qa = {f"qa:c{i}": (False, {}) for i in range(4)}
        m = self.check([{"id": k, "kind": "qa"} for k in qa], qa=qa)
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("…", m.detail)
        self.setUp()
        qa3 = dict(list(qa.items())[:3])
        self.assertNotIn("…", self.check([{"id": k, "kind": "qa"} for k in qa3], qa=qa3).detail)


class KillTddBranches(unittest.TestCase):
    def ev(self, *runs):
        return Evidence(story_id=SID, events=[Event(kind="tool_run", name="test", ok=ok, detail=d, seq=i + 1) for i, (ok, d) in enumerate(runs)])

    def test_runs_before_the_last_green_are_the_non_ok_non_skipped_ones(self):
        e = self.ev((True, {}), (False, {"skipped": "x"}), (False, {"n": 1}), (True, {}))
        self.assertEqual([x.detail for x in tdd.runs_before_last_green(e)], [{"n": 1}])

    def test_subjects_are_the_criterion_tests_else_the_added_files_tests(self):
        a, b, c = "tests/test_x.py::test_AC_S_01_1_a", "tests/test_x.py::test_plain", "tests/other.py::test_b"
        d = {"test_ids": [a, b, c]}
        self.assertEqual(tdd.tdd_subjects(d, SID, 1, ["tests/test_x.py"]), [a])
        self.assertEqual(tdd.tdd_subjects(d, SID, 0, ["tests/test_x.py"]), [a, b])
        self.assertEqual(tdd.tdd_subjects({"test_ids": [b, c]}, SID, 1, ["tests/test_x.py"]), [b])
        self.assertEqual(tdd.tdd_subjects({"test_ids": ["plain title"]}, SID, 0, ["plain title"]), [])

    def test_a_red_run_failing_on_a_symbol_the_storys_changed_module_supplies_is_the_red(self):
        t = "tests/test_x.py::test_AC_S_01_1_a"
        red = {"test_format": "pytest", "test_ids": [t], "failed_ids": [t],
               "failure_imports": {t: {"missing_module": "src.a", "missing_name": "f"}}, "output_complete": True}
        e = self.ev((False, red), (True, {"test_format": "pytest", "test_ids": [t]}))
        self.assertIsNotNone(tdd.proven_red_before_green(e, SID, acceptance=1, added_tests=["tests/test_x.py"], changed=["src/a.py"]))
        self.assertIsNone(tdd.proven_red_before_green(e, SID, acceptance=1, added_tests=["tests/test_x.py"], changed=[]))


class KillLedgerBranches(unittest.TestCase):
    def led(self, **stories):
        led = L.Ledger()
        for sid, (acc, covers) in stories.items():
            led.stories[sid] = L.StoryLine(id=sid, acceptance=acc, covers=list(covers))
        return led

    def observe(self, led, detail, ok=True, sid="S-01", **kw):
        class E:
            name = "test"
        E.ok, E.detail = ok, detail
        L._observe_tests(led, E(), sid, 1, "aaa", 1.0, **kw)
        return led.behaviors

    def test_a_run_needs_a_reporter_and_names_to_be_read(self):
        for det in ({"test_format": "pytest", "test_ids": []}, {"test_ids": ["tests/t.py::test_AC_S_01_1_x"]}):
            with self.subTest(det=det):
                b = self.observe(self.led(**{"S-01": (1, [])}), det)
                self.assertTrue(str(b["AC-S-01-1"].source.get("why")).startswith(L.WHY_UNREADABLE))

    def test_the_unreadable_reason_carries_its_cause(self):
        b = self.observe(self.led(**{"S-01": (1, [])}), {"unrunnable": "boom"}, ok=False)
        self.assertEqual(b["AC-S-01-1"].source.get("why"), f"{L.WHY_UNREADABLE}: boom")

    def test_a_story_without_criteria_rolls_nothing_up(self):
        b = self.observe(self.led(**{"S-01": (0, ["FR-1"])}), {"test_format": "pytest", "test_ids": ["t"], "failed_ids": ["t"]}, ok=False)
        self.assertNotIn("FR-1", b)

    def test_green_wins_for_a_requirement_several_stories_cover(self):
        det = {"test_format": "pytest", "test_ids": ["tests/t.py::test_AC_S_01_1_x", "tests/t.py::test_AC_S_02_1_y"],
               "failed_ids": ["tests/t.py::test_AC_S_02_1_y"]}
        b = self.observe(self.led(**{"S-01": (1, ["FR-1"]), "S-02": (1, ["FR-1"])}), det, ok=False)
        self.assertEqual(b["FR-1"].status, L.VERIFIED)

    def test_among_equal_verdicts_the_first_story_judged_keeps_the_requirement(self):
        ids = ["tests/t.py::test_AC_S_01_1_x", "tests/t.py::test_AC_S_02_1_y"]
        for failed in ([], ids):
            with self.subTest(failed=failed):
                b = self.observe(self.led(**{"S-01": (1, ["FR-1"]), "S-02": (1, ["FR-1"])}),
                                 {"test_format": "pytest", "test_ids": ids, "failed_ids": failed}, ok=not failed)
                self.assertEqual(b["FR-1"].source.get("story"), "S-01")

    def test_a_requirement_inherits_the_not_executed_reason_only_on_a_landed_candidate(self):
        det = {"test_format": "pytest", "test_ids": ["tests/t.py::test_AC_S_01_1_x"], "skipped_ids": ["tests/t.py::test_AC_S_01_1_x"]}
        self.assertEqual(self.observe(self.led(**{"S-01": (1, ["FR-1"])}), det)["FR-1"].source.get("why"), L.WHY_NOT_EXECUTED)
        b = self.observe(self.led(**{"S-01": (1, ["FR-1"])}), det, landed=False)
        self.assertEqual(b["FR-1"].source.get("why"), "story criteria not yet green")

    def test_criteria_green_make_the_requirement_green_even_in_a_red_run(self):
        det = {"test_format": "pytest", "test_ids": ["tests/t.py::test_AC_S_01_1_x", "tests/t.py::test_other"],
               "failed_ids": ["tests/t.py::test_other"]}
        self.assertEqual(self.observe(self.led(**{"S-01": (1, ["FR-1"])}), det, ok=False)["FR-1"].status, L.VERIFIED)


class KillMemoryResolveOnWindows(unittest.TestCase):
    r"""SS-91 — CI windows 2026-09-18: `realpath` kept the `\\?\` prefix for a store another writer was replacing."""

    def test_the_extended_length_prefix_is_dropped(self):
        from unittest import mock

        from aisef import memory
        with mock.patch.object(memory.Path, "resolve", lambda self: memory.Path("\\\\?\\C:\\p\\store.json")):
            self.assertEqual(str(memory._resolved("x")), "C:\\p\\store.json")
        with mock.patch.object(memory.Path, "resolve", lambda self: memory.Path("\\\\?\\UNC\\srv\\share\\x")):
            self.assertEqual(str(memory._resolved("x")), "\\\\srv\\share\\x")

    def test_a_store_path_resolved_with_the_prefix_is_still_inside_the_project(self):
        from unittest import mock

        from aisef import memory
        real = memory.Path.resolve
        with tempfile.TemporaryDirectory() as td:
            def flicker(self):
                r = real(self)
                return memory.Path("\\\\?\\" + str(r)) if r.name == "store.json" else r
            with mock.patch.object(memory.Path, "resolve", flicker):
                self.assertEqual(memory.safe_path(td, "_bmad-output/memory/store.json").name, "store.json")

if __name__ == "__main__":
    unittest.main()
