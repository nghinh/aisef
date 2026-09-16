"""Story-baseline provenance (D-033, lỗi 187) — the regression baseline is immutable within a story epoch.

Measured on aisef 1.7.4 (public wheel, LedgerLock OpenCode replay, STORY-03-01, 2026-09-16):
`run_baseline` ran at the worktree HEAD on every `implement_story` invocation, so a story resumed
from its own branch re-baselined at its previous candidate (evidence seq 393: parent ca37cc44,
base_ref 9cf22f5c), and `gate._baseline_check` read `evidence.last(TOOL_RUN, BASELINE_RUN)` — the
newest record. The story's own earlier tests became "tests present at baseline"; renaming two of
them (dropping a wrong AC code) on the next candidate failed the gate ("lost 2 tests present at
baseline", evidence seqs [393, 1694]) although nothing present at story entry (seq 2, parent =
branch point 9cf22f5c) was lost. A correct candidate could not complete without operator intervention.

Owner invariant (2026-09-16): the authoritative baseline is captured from the integrated parent at
story entry; retries, resumes and verify-only reuse that exact record; a candidate produced by the
story never becomes its baseline; a new baseline exists only for a new story epoch (contract
changed) and is taken from the integrated parent; absent or provenance-invalid → fail closed.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tests  # noqa: E402,F401 — HostProvider in place of docker (tests/__init__.py)

from aisef.config import DEFAULTS, Config  # noqa: E402
from aisef.control import gate  # noqa: E402
from aisef.control.normalize import Story  # noqa: E402
from aisef.control.outcome import Outcome  # noqa: E402
from aisef.harness.observe import NOTE, TOOL_RUN, Event, EvidenceStore  # noqa: E402
from aisef.harness.tools import BASELINE_RUN  # noqa: E402
from aisef.phases import implement as I  # noqa: E402

SID = "STORY-03-01"
ENTRY = "9cf22f5c7fb87b5b58e3ea330b49c0b108768deb"       # branch point (story entry)
ENTRY2 = "1111111111111111111111111111111111111111"      # integrated parent of a later epoch
C1 = "ca37cc44c0989fb32d8d575adea590d669d7b9a8"          # the story's own candidate (run 1)
C2 = "01c1d304960970d0388d5da38736c420037db240"          # the story's candidate (run 2)
C3 = "3333333333333333333333333333333333333333"
PRE = ["tests/test_conflict.py::TestReplay::test_AC_STORY_01_06_1_same_rid_is_idempotent",
       "tests/test_format.py::TestNormalize::test_AC_STORY_01_01_1_nfc"]
CLS = "tests/test_atomic_batch.py::TestApplyBatchProcessWideLock"
OWN_WRONG = [f"{CLS}::test_AC_STORY_03_01_6_concurrent_apply_batch_calls_serialize_via_lock",
             f"{CLS}::test_AC_STORY_03_01_6_ledger_has_a_process_wide_lock_attribute"]
OWN_FIXED = [f"{CLS}::test_concurrent_apply_batch_calls_serialize_via_lock",
             f"{CLS}::test_ledger_has_a_process_wide_lock_attribute"]
CONTRACT = "story:contract"


def _baseline(ids, *, parent, base_ref, **extra) -> Event:
    return Event(kind=TOOL_RUN, name=BASELINE_RUN, ok=True, detail={
        "baseline": True, "parent": parent, "base_ref": base_ref, "red_before": [],
        "test_format": "pytest", "test_ids": list(ids), "failed_ids": [], "skipped_ids": [], **extra})


def _test(ids, *, candidate) -> Event:
    return Event(kind=TOOL_RUN, name="test", ok=True, detail={
        "candidate": candidate, "test_format": "pytest", "test_ids": list(ids), "failed_ids": [], "skipped_ids": []})


def _contract(fp) -> Event:
    return Event(kind=NOTE, name=CONTRACT, detail={"fingerprint": fp, "codes": {}})


class TestGateSelectsTheStoryEntryBaseline(unittest.TestCase):
    """Consumer side: `no baseline regression` scores against the story-entry baseline."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = EvidenceStore(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _entry_and_first_attempt(self):
        self.store.record(SID, _contract("fp-1"))
        self.store.record(SID, _baseline(PRE, parent=ENTRY, base_ref=ENTRY))      # story-entry baseline
        self.store.record(SID, _test(PRE + OWN_WRONG, candidate=C1))             # the story added two tests

    def _resumed_rebaseline(self):
        # 1.7.4 shape: a resumed run re-baselined at the story's own candidate
        self.store.record(SID, _baseline(PRE + OWN_WRONG, parent=C1, base_ref=ENTRY))

    def _entry_record(self):
        return next(e for e in self.store.read(SID).of(TOOL_RUN, BASELINE_RUN) if e.detail.get("parent") == ENTRY)

    def test_control_entry_baseline_alone_passes_the_renamed_candidate(self):
        self._entry_and_first_attempt()
        self.store.record(SID, _test(PRE + OWN_FIXED, candidate=C2))
        check = gate._baseline_check(self.store.read(SID), C2)
        self.assertTrue(check.passed, check.detail)

    def test_F_resumed_rebaseline_at_the_story_candidate_cannot_report_its_own_renamed_tests_as_lost(self):
        self._entry_and_first_attempt()
        self._resumed_rebaseline()
        self.store.record(SID, _test(PRE + OWN_FIXED, candidate=C2))
        check = gate._baseline_check(self.store.read(SID), C2)
        self.assertTrue(check.passed, f"got: {check.detail} (evidence {check.evidence})")
        self.assertEqual(check.evidence[0], self._entry_record().seq, "scored against the story-entry record")

    def test_E_story_generated_tests_from_an_earlier_attempt_are_not_baseline_tests(self):
        self._entry_and_first_attempt()
        self._resumed_rebaseline()
        self.store.record(SID, _test(PRE, candidate=C2))                      # the story dropped its own tests
        check = gate._baseline_check(self.store.read(SID), C2)
        self.assertTrue(check.passed, check.detail)

    def test_I_genuine_deletion_of_a_pre_existing_test_is_still_detected(self):
        self._entry_and_first_attempt()
        self._resumed_rebaseline()
        self.store.record(SID, _test(PRE[1:] + OWN_FIXED, candidate=C2))      # a story-entry test is gone
        check = gate._baseline_check(self.store.read(SID), C2)
        self.assertFalse(check.passed)
        self.assertIn("lost 1 tests present at baseline", check.detail)
        self.assertIn(PRE[0], check.detail)

    def test_H_only_a_candidate_rooted_record_exists_fails_closed(self):
        self.store.record(SID, _contract("fp-1"))
        self._resumed_rebaseline()                                            # no story-entry baseline at all
        self.store.record(SID, _test(PRE + OWN_FIXED, candidate=C2))
        check = gate._baseline_check(self.store.read(SID), C2)
        self.assertIs(check.outcome, Outcome.UNRUNNABLE, f"{check.outcome} {check.detail}")
        self.assertIn("BASELINE_UNAVAILABLE", check.detail)

    def test_H2_no_baseline_record_at_all_stays_not_applicable(self):
        """Old journals never recorded a baseline; that is 'cannot compare', not a provenance failure."""
        self.store.record(SID, _test(PRE, candidate=C2))
        check = gate._baseline_check(self.store.read(SID), C2)
        self.assertIs(check.outcome, Outcome.NOT_APPLICABLE)

    def test_G_a_new_story_epoch_scores_against_the_baseline_captured_for_that_epoch(self):
        self._entry_and_first_attempt()
        self.store.record(SID, _contract("fp-2"))                              # criteria changed → new epoch
        self.store.record(SID, _baseline(PRE, parent=ENTRY2, base_ref=ENTRY2, root=ENTRY2, epoch="fp-2"))
        self.store.record(SID, _test(PRE + ["tests/test_new.py::test_AC_STORY_03_01_1_x"], candidate=C3))
        ev = self.store.read(SID)
        check = gate._baseline_check(ev, C3)
        self.assertTrue(check.passed, check.detail)
        new = next(e for e in ev.of(TOOL_RUN, BASELINE_RUN) if e.detail.get("epoch") == "fp-2")
        self.assertEqual(check.evidence[0], new.seq)

    def test_G2_a_baseline_from_an_earlier_epoch_is_not_reused_after_the_contract_changed(self):
        self._entry_and_first_attempt()
        self.store.record(SID, _contract("fp-2"))
        self.store.record(SID, _test(PRE, candidate=C3))
        check = gate._baseline_check(self.store.read(SID), C3)
        self.assertIs(check.outcome, Outcome.UNRUNNABLE, f"{check.outcome} {check.detail}")
        self.assertIn("BASELINE_UNAVAILABLE", check.detail)


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          encoding="utf-8").stdout.strip()


class TestBaselineProducer(unittest.TestCase):
    """Producer side: `run_baseline` captures once per story epoch, at the integrated parent."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)
        _git(self.project, "init", "-q")
        _git(self.project, "config", "user.email", "t@t.t")
        _git(self.project, "config", "user.name", "t")
        fake = self.project / "fake_pytest.sh"
        fake.write_text("#!/bin/sh\nprintf 'tests/test_a.py::test_a PASSED\\ntests/test_b.py::test_b PASSED\\n'\n",
                        encoding="utf-8")
        fake.chmod(0o755)
        (self.project / "src").mkdir()
        (self.project / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
        _git(self.project, "add", "-A")
        _git(self.project, "commit", "-qm", "entry")
        self.entry = _git(self.project, "rev-parse", "HEAD")
        self.root = self.project / "_bmad-output"
        self.root.mkdir()
        self.story = Story(id=SID, epic_id="EPIC-03", title="t", acceptance_criteria=["AC one", "AC two"],
                           covers=["FR-1"], write_scope=["src"])
        self.cfg = Config({**DEFAULTS, "tools.test": str(fake), "tools.lint": "true",
                           "sandbox.use_docker": False, "run.max_retries": 1})

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self):
        I.run_baseline(self.story, workdir=self.project, artifact_root=self.root, config=self.cfg,
                       base_ref=self.entry)

    def _records(self):
        return list(EvidenceStore(self.root).read(SID).of(TOOL_RUN, BASELINE_RUN))

    def _commit(self, name):
        (self.project / "src" / name).write_text("y = 2\n", encoding="utf-8")
        _git(self.project, "add", "-A")
        _git(self.project, "commit", "-qm", name)
        return _git(self.project, "rev-parse", "HEAD")

    def test_A_first_execution_records_the_baseline_at_the_story_entry_parent(self):
        self._run()
        (rec,) = self._records()
        d = rec.detail
        self.assertEqual(d["parent"], self.entry)
        self.assertEqual(d["base_ref"], self.entry)
        self.assertEqual(d.get("root"), self.entry, "baseline root = integrated parent at story entry")
        self.assertTrue(d.get("epoch"), "baseline carries the story epoch (contract fingerprint)")
        self.assertEqual(sorted(d["test_ids"]), ["tests/test_a.py::test_a", "tests/test_b.py::test_b"])

    def test_B_a_retry_within_the_same_run_keeps_the_same_baseline(self):
        self._run()
        self._run()
        self.assertEqual(len(self._records()), 1)
        self.assertIn("baseline REUSED", (self.root / "run.log").read_text(encoding="utf-8"))

    def test_C_a_resumed_run_keeps_the_same_baseline_and_never_rebaselines_at_the_story_head(self):
        self._run()
        c1 = self._commit("b.py")                                             # the story's own candidate
        self.assertNotEqual(c1, self.entry)
        self._run()                                                           # later `aisef run`: HEAD = c1
        (rec,) = self._records()
        self.assertEqual(rec.detail["parent"], self.entry)

    def test_D_verify_only_reuses_the_story_baseline_and_records_none(self):
        from tests.test_implement import ScriptedClient
        self._run()
        out = I.verify_only(self.story, project=self.project, workdir=self.project, artifact_root=self.root,
                            client=ScriptedClient(), config=self.cfg)
        self.assertEqual(len(self._records()), 1, "verify-only must not create a baseline")
        chk = [c for c in out.attempts[-1].gate.checks if c.name == "no baseline regression"][0]
        self.assertEqual(chk.evidence[0], self._records()[0].seq)

    def test_G_a_new_epoch_captures_a_new_baseline_from_the_integrated_parent(self):
        self._run()
        first = self._records()[0].detail
        self.story.acceptance_criteria = ["AC one", "AC two (owner arbitration)"]   # contract changed
        _git(self.project, "checkout", "-q", self.entry)                         # branch dropped → back at the parent
        self._run()
        recs = self._records()
        self.assertEqual(len(recs), 2)
        self.assertNotEqual(recs[1].detail.get("epoch"), first.get("epoch"))
        self.assertEqual(recs[1].detail["parent"], self.entry)
        self.assertEqual(recs[1].detail.get("root"), self.entry)

    def test_H_a_new_epoch_without_the_integrated_parent_fails_closed_instead_of_rebaselining(self):
        self._run()
        c1 = self._commit("b.py")
        self.story.acceptance_criteria = ["AC one", "AC two (owner arbitration)"]   # contract changed, HEAD ≠ parent
        self._run()
        recs = self._records()
        self.assertEqual(len(recs), 2)
        d = recs[1].detail
        self.assertTrue(str(d.get("unrunnable", "")).startswith("BASELINE_UNAVAILABLE"), d)
        self.assertNotIn("test_ids", d, "no test run at the story's own build")
        ev = EvidenceStore(self.root).read(SID)
        self.assertIs(gate._baseline_check(ev, c1).outcome, Outcome.UNRUNNABLE)


if __name__ == "__main__":
    unittest.main()
