"""Phase 8A, group A — discovery-debt resolution for seven NEEDS_TEST sibling sites
(closure-evidence/hardening/sibling-scan.json): SS-01, SS-06, SS-07, SS-29, SS-31, SS-32, SS-33.

Every test asserts the INVARIANT (docs/INVARIANTS.md). A test marked ``expectedFailure`` under its SS id
is a CONFIRMED defect on the 1.7.6 baseline (the comment states the observed wrong behaviour); a green test
is a negative control and its comment states which line makes the code safe by construction. Each test
proves the suspicious path was reached (an intermediate assertion on the evidence or the framework's own
reader) before asserting the invariant. No OpenCode, no network, no Docker (tests/__init__.py swaps the
host provider in).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import tests  # noqa: E402,F401

from aisef.control import closure as CL  # noqa: E402
from aisef.control import gate  # noqa: E402
from aisef.control.experience import parse_experience  # noqa: E402
from aisef.control.outcome import Check, Outcome  # noqa: E402
from aisef.harness import testlog  # noqa: E402  — module import: `TestLog` in this namespace trips pytest collection
from aisef.harness.observe import TOOL_RUN, EvidenceStore  # noqa: E402
from aisef.harness.tools import BASELINE_RUN  # noqa: E402
from aisef.phases import implement as I  # noqa: E402
from tests import test_closure as TC  # noqa: E402  — module import: binding TestG6 here would re-collect it
from tests.hardening.test_sibling_scan import C1, C2, SID, _check, _ev, _git  # noqa: E402
from tests.test_retry_hygiene import Developer, HygieneCase, in_scope_fix  # noqa: E402


def _probe_ctx(cid: str, probe: str, corpus: TC.Corpus, cleanup) -> CL.Ctx:
    repo = TC.Repo(TC.spec_of(TC.crit(cid, f"aisef.control.closure:{probe}")))
    cleanup(repo.close)
    return repo.ctx({}, corpus=str(corpus.root))


# ---------------------------------------------------------------- FAM-OUTCOME / INV-T.1

class TestSS01RealTestsNeedsARecordedScan(unittest.TestCase):
    """SS-01 — `real tests` (gate.py ~767-776) scores PASSED when no `qa:fake-tests` record exists:
    "scan never ran" reads exactly like "scan ran clean". INV-T.1: absence never produces a PASS."""

    # GREEN since F2 (SS-01: absence and truncation are UNRUNNABLE, never PASS), 2026-09-16
    def test_no_fake_tests_record_is_not_a_pass(self):
        ev = _ev({"kind": TOOL_RUN, "name": "test", "ok": True,
                  "detail": {"candidate": C1, "test_format": "pytest", "test_ids": []}},
                 {"kind": TOOL_RUN, "name": "lint", "ok": True, "detail": {"candidate": C1}})
        self.assertIsNone(ev.last(TOOL_RUN, gate.FAKE_TESTS))        # the scan left no record at all
        g = gate.evaluate(SID, ev, changed=["src/a.py"], write_scope=["src"], screens=[],
                          candidate=C1, review_blocking=[])
        c = _check(g, "real tests")
        self.assertIsNot(c.outcome, Outcome.PASSED,
                         f"`real tests` scored {c.outcome.value} with no qa:fake-tests record (evidence={c.evidence})")


class TestSS01StoryPathAlwaysRecordsTheScan(HygieneCase):
    """SS-01 bound — negative control: `verify_candidate` (implement.py ~1057-1059) writes `qa:fake-tests`
    on every attempt, `ok=not fake`, even when the developer touched no test file, so in the story path
    the gate never meets the absence case; only manual/`aisef qa` evidence can (qa.run_suite ~753 records
    only when fakes are found). Real repo + worktree: `ImplementTestCase` has no entry commit and never freezes."""

    def test_verify_candidate_records_a_clean_scan_when_no_test_file_changed(self):
        out = self.implement(Developer(first=in_scope_fix))          # writes ledgerlock/cli.py only
        cand = out.attempts[-1].candidate
        self.assertTrue(cand and cand != self.entry, out.summary())  # a frozen candidate, not the entry commit
        touched = _git(self.project, "show", "--name-only", "--format=", cand).split()
        self.assertEqual(touched, ["ledgerlock/cli.py"], touched)   # no test file in the candidate
        recs = [e for e in EvidenceStore(self.artifacts).read(self.story.id).of(TOOL_RUN, gate.FAKE_TESTS)
                if e.detail.get("candidate") == cand]
        self.assertEqual([(e.ok, e.detail.get("files")) for e in recs], [(True, [])])


MAX_IDS = testlog.MAX_IDS


def _log(passed, failed=()) -> dict:
    return testlog.TestLog(format="pytest", passed=list(passed), failed=list(failed)).to_evidence()


class TestSS33TruncationNeverYieldsAVacuousPass(unittest.TestCase):
    """SS-33 — testlog caps every id list at MAX_IDS (500); `no baseline regression` (gate.py ~397-430)
    disables `lost`/`renamed` under truncation but still reports PASSED, and `newly_red` is computed only
    over the surviving 500 baseline names. INV-T.1: a comparison that cannot see the test cannot PASS."""

    IDS = [f"tests/test_big.py::test_{i:03d}" for i in range(MAX_IDS + 100)]
    VICTIM = IDS[MAX_IDS + 50]                                        # beyond the cut at both ends

    def _gate(self, candidate_log: dict, *, ok: bool) -> gate.StoryGate:
        ev = _ev({"kind": TOOL_RUN, "name": BASELINE_RUN, "ok": True,
                  "detail": {"baseline": True, "root": C2, "parent": C2, "base_ref": C2, "epoch": "e1",
                             "red_before": [], **_log(self.IDS)}},
                 {"kind": TOOL_RUN, "name": "test", "ok": ok, "detail": {"candidate": C1, **candidate_log}},
                 {"kind": TOOL_RUN, "name": "lint", "ok": True, "detail": {"candidate": C1}})
        base = gate.authoritative_baseline(ev)
        self.assertEqual(len(base.detail["test_ids"]), MAX_IDS)      # the real truncation, not a fixture's
        self.assertNotIn(self.VICTIM, base.detail["test_ids"])       # green at baseline, name cut off
        return gate.evaluate(SID, ev, changed=["src/a.py"], write_scope=["src"], screens=[],
                             candidate=C1, review_blocking=[])

    # GREEN since F2 (SS-33a: absence and truncation are UNRUNNABLE, never PASS), 2026-09-16
    def test_a_baseline_green_test_beyond_the_cut_turning_red_is_not_a_pass(self):
        cand = _log([t for t in self.IDS if t != self.VICTIM], failed=[self.VICTIM])
        self.assertIn(self.VICTIM, cand["failed_ids"])               # the gate CAN see it is red …
        self.assertNotIn(self.VICTIM, cand["test_ids"])              # … and cannot see it was green at baseline
        c = _check(self._gate(cand, ok=False), "no baseline regression")
        self.assertIsNot(c.outcome, Outcome.PASSED, f"{c.outcome.value}: {c.detail}")

    # GREEN since F2 (SS-33b: absence and truncation are UNRUNNABLE, never PASS), 2026-09-16
    def test_a_baseline_test_deleted_beyond_the_cut_is_not_a_pass(self):
        g = self._gate(_log([t for t in self.IDS if t != self.VICTIM]), ok=True)
        c = _check(g, "no baseline regression")
        self.assertIsNot(c.outcome, Outcome.PASSED, f"{c.outcome.value}: {c.detail} · gate passed={g.passed}")


# ---------------------------------------------------------------- FAM-RELEASE / INV-R.2, INV-F.3

class TestSS06CorpusHistoryMeansAncestry(unittest.TestCase):
    """SS-06 — G4.5 (closure.py ~802) asks `rev-parse --verify <cand>^{commit}`: object existence. A
    candidate frozen on a story branch nobody merged lives in the same object store. INV-R.2: ancestry."""

    @unittest.expectedFailure   # SS-06 — observed: PASSED "1 stories verified at a merged candidate" for an unmerged branch SHA
    def test_a_candidate_on_an_unmerged_branch_is_not_in_the_corpus_history(self):
        corpus = TC.Corpus()
        self.addCleanup(corpus.close)
        tree = TC.git(corpus.root, "rev-parse", "HEAD^{tree}").stdout.strip()
        cand = TC.git(corpus.root, "commit-tree", tree, "-p", "HEAD", "-m", "S-1 candidate, never merged").stdout.strip()
        TC.git(corpus.root, "update-ref", "refs/heads/story/S-1", cand)
        self.assertEqual(TC.git(corpus.root, "rev-parse", "--verify", f"{cand}^{{commit}}").returncode, 0)
        self.assertNotEqual(TC.git(corpus.root, "merge-base", "--is-ancestor", cand, "HEAD").returncode, 0)
        store = EvidenceStore(corpus.art, candidate=cand)
        for name in ("test", "review", "security"):
            store.tool_run("S-1", name, ok=True)                     # latest of every check: at the branch SHA
        self.assertEqual(store.read("S-1").candidate, cand)
        p = CL.probe_evidence_at_candidate(_probe_ctx("G4.5", "probe_evidence_at_candidate", corpus, self.addCleanup))
        self.assertIs(p.outcome, Outcome.FAILED, f"{p.outcome.value}: {p.detail}")


class TestSS07ARecordedReviewIsAVerdict(unittest.TestCase):
    """SS-07 — G4.4 (closure.py ~758-760) counts any `TOOL_RUN review` as "review recorded"; the story
    loop itself writes one for a reviewer that did NOT execute (`outcome: REVIEW_UNRUNNABLE`, D-032), and
    its own `_review_complete` refuses to reuse that record. INV-R.2/F.3: absence of a stage is not a stage."""

    @unittest.expectedFailure   # SS-07 — observed: PASSED "review and security recorded" on a REVIEW_UNRUNNABLE-only record
    def test_an_unrunnable_review_record_does_not_count_as_review_recorded(self):
        corpus = TC.Corpus(review=False)
        self.addCleanup(corpus.close)
        store = EvidenceStore(corpus.art, candidate=corpus.head)
        store.tool_run("S-1", "review", ok=False, detail={"findings": [], "plan": [], "attempt": 1,
                                                         "outcome": I.REVIEW_UNRUNNABLE,
                                                         "unrunnable": "exceeded 1800s", "review_attempt": 3})
        store.tool_run("S-1", "security", ok=True)
        recs = store.read("S-1").of(TOOL_RUN, "review")
        self.assertEqual(len(recs), 1)
        self.assertFalse(I._review_complete(recs[0]))                 # the framework's own reader: no verdict here
        p = CL.probe_review_and_security(_probe_ctx("G4.4", "probe_review_and_security", corpus, self.addCleanup))
        self.assertIsNot(p.outcome, Outcome.PASSED, f"{p.outcome.value}: {p.detail}")


# ---------------------------------------------------------------- FAM-PROSE / INV-F.2

class TestSS29ResolvedIsAStatusNotASubstring(unittest.TestCase):
    """SS-29 — G6.3 (closure.py ~1598) closes a finding when any RESOLVED marker is a substring of its
    status cell; `unresolved`, `not resolved`, `will be fixed` all contain one. INV-R.2/F.2."""

    # GREEN since F3 (SS-29: prose has no authority over control state), 2026-09-16
    def test_an_open_p1_blocker_worded_unresolved_does_not_pass_g6_3(self):
        fx = TC.TestG6("test_an_unresolved_p0_blocker_fails")
        fx.setUp()
        self.addCleanup(fx.doCleanups)
        row = "| docs gap | P2 | open |"
        for status in ("open", "unresolved", "not resolved", "will be fixed in 1.8"):
            fx.record(TC.RECORD.replace(row, f"| cannot install | P1 | {status} |"))
            p = CL.probe_onboarding_blockers(fx.repo.ctx(fx.criterion()))
            self.assertIs(p.outcome, Outcome.FAILED, f"status {status!r}: {p.outcome.value} — {p.detail}")


class TestSS31NoSurfaceIsAnchoredToTheStatement(unittest.TestCase):
    """SS-31 — `_NO_SURFACE` (experience.py ~177) accepts `Screens: none` followed within 120 chars by any
    of ~15 keywords (`API`, `service`, …). mockup.py:192 consults `headless` exactly when the document has
    no screen table — the case where the prose is the only source. INV-F.2."""

    # GREEN since F3 (SS-31: prose has no authority over control state), 2026-09-16
    def test_a_line_that_announces_screens_is_not_headless(self):
        self.assertTrue(parse_experience("**Screens:** none — no graphical surface (CLI)\n").headless)
        prose = ("Screens: none of the legacy screens are kept; the new dashboard has three screens, "
                 "each backed by the billing API.\n")
        exp = parse_experience(prose)
        self.assertEqual(exp.screens, [])                            # no table: `headless` decides the contract
        self.assertFalse(exp.headless, "a sentence announcing three screens was read as `no graphical surface`")


class TestSS32DeadlockDiagnosisReadsDataNotProse(unittest.TestCase):
    """SS-32 — `nop_deadlock` (implement.py ~2714) re-derives the still-green criteria by regexing the
    English sentence gate.py ~559 emits; `Check` carries no structured criteria field. INV-F.2."""

    IDS = "todo.spec.js > AC-STORY-01-01-1 adds an item, todo.spec.js > AC-STORY-01-01-2 lists items"

    def _attempts(self, detail: str) -> list[I.Attempt]:
        return [I.Attempt(number=n, candidate=C1,
                          gate=gate.StoryGate(SID, [Check("tests verify story", False, detail)])) for n in (1, 2)]

    # GREEN since F3 (SS-32: prose has no authority over control state), 2026-09-16
    def test_rewording_the_gate_sentence_does_not_silence_the_diagnosis(self):
        produced = f"tests verify nothing — still green without story code (parent SHA abc1234): {self.IDS}"
        self.assertIn("AC-STORY-01-01-1", I.nop_deadlock(self._attempts(produced)))   # today's wording: diagnosed
        reworded = f"tests verify nothing — green with the story's code absent (parent SHA abc1234): {self.IDS}"
        self.assertIn("AC-STORY-01-01-1", I.nop_deadlock(self._attempts(reworded)),
                      "the diagnosis vanished when the sentence changed: the consumer reads prose, Check has no data")


if __name__ == "__main__":
    unittest.main()
