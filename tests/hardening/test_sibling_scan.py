"""Phase 3 — global sibling-bug sweep: deterministic RED reproducers for the candidates the sweep
CONFIRMED (closure-evidence/hardening/sibling-scan.json). Every test here asserts the INVARIANT
(docs/INVARIANTS.md), so it is red on the 1.7.6 baseline and marked ``expectedFailure`` under its
SS id; an unexpected success means the hypothesis was wrong and the entry must be reclassified.
No OpenCode, no network, no Docker (tests/__init__.py swaps the host provider in).
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import tests  # noqa: E402,F401

from aisef.clients.stream import RunResult, exit_status_of  # noqa: E402
from aisef.config import DEFAULTS, Config  # noqa: E402
from aisef.control import gate  # noqa: E402
from aisef.control.budget import BudgetExceeded  # noqa: E402
from aisef.control.machine_gate import _GIU_CHO  # noqa: E402
from aisef.control.normalize import Story  # noqa: E402
from aisef.control.outcome import Outcome  # noqa: E402
from aisef.control.security import SecurityReport, parse as parse_security  # noqa: E402
from aisef.control.worktree import WorktreeManager, commit_paths  # noqa: E402
from aisef.harness.guardrails import changed_files  # noqa: E402
from aisef.harness.observe import AGENT_RUN, GUARD_SEEN, NOTE, TOOL_RUN, Event, Evidence, EvidenceStore  # noqa: E402
from aisef.harness.tools import NO_SETUP, unrunnable_reason  # noqa: E402
from aisef.phases import implement as I  # noqa: E402
from tests.test_implement import ImplementTestCase, ScriptedClient  # noqa: E402
from tests.test_retry_hygiene import Developer, HygieneCase, ledgerlock_pattern  # noqa: E402

SID = "STORY-01-01"
C1 = "1111111111111111111111111111111111111111"
C2 = "2222222222222222222222222222222222222222"


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout.strip()


def _ev(*events) -> Evidence:
    return Evidence(story_id=SID, events=[Event(seq=i + 1, at=float(i + 1), **e) for i, e in enumerate(events)])


def _check(g, name):
    return next(c for c in g.checks if c.name == name)


# ---------------------------------------------------------------- FAM-IDENTITY / INV-D, INV-E

class TestSS02GuardHeartbeatIsBoundToTheGradedSession(unittest.TestCase):
    """SS-02 — `guard ran` reads a once-per-story, unstamped GUARD_SEEN heartbeat; a later attempt whose
    session left no guard trace still passes. Invariant D/E: a proof binds to the graded session."""

    @unittest.expectedFailure   # SS-02
    def test_a_heartbeat_from_attempt_1_does_not_prove_attempt_2s_guard_ran(self):
        ev = _ev(
            {"kind": GUARD_SEEN, "name": "write-scope", "detail": {"tool": "Write"}},
            {"kind": AGENT_RUN, "name": f"{SID}#1", "detail": {"role": "developer"}},
            {"kind": TOOL_RUN, "name": "test", "ok": True, "detail": {"candidate": C1, "test_format": "pytest", "test_ids": []}},
            {"kind": NOTE, "name": "gate:verdict", "ok": False, "detail": {"candidate": C1, "attempt": 1, "failures": ["review"]}},
            {"kind": AGENT_RUN, "name": f"{SID}#2", "detail": {"role": "developer"}},   # no guard event in this session
            {"kind": TOOL_RUN, "name": "test", "ok": True, "detail": {"candidate": C2, "test_format": "pytest", "test_ids": []}},
            {"kind": TOOL_RUN, "name": "lint", "ok": True, "detail": {"candidate": C2}},
        )
        g = gate.evaluate(SID, ev, changed=["src/a.py"], write_scope=["src"], screens=[], guard_expected=True,
                          candidate=C2, review_blocking=[])
        self.assertIsNot(_check(g, "guard ran").outcome, Outcome.PASSED,
                         "attempt 2's session has no guard trace; attempt 1's heartbeat is not about it")


class TestSS03CriteriaProofBindsToTheCandidate(unittest.TestCase):
    """SS-03 — `criteria have tests` harvests test ids from ANY green `qa:*` run kept by `for_candidate`,
    including unstamped runs from before the freeze. Invariant D: a proof carries the candidate."""

    @unittest.expectedFailure   # SS-03
    def test_an_unstamped_qa_run_cannot_satisfy_a_criterion_the_candidates_run_does_not(self):
        ev = _ev(
            {"kind": TOOL_RUN, "name": "qa:unit", "ok": True,          # pre-freeze, unstamped
             "detail": {"test_format": "pytest", "test_ids": [f"tests/test_a.py::test_AC_{SID.replace('-', '_')}_1_ok"]}},
            {"kind": TOOL_RUN, "name": "test", "ok": True,             # the candidate's own run: no criterion test
             "detail": {"candidate": C1, "test_format": "pytest", "test_ids": ["tests/test_a.py::test_plain"]}},
            {"kind": TOOL_RUN, "name": "lint", "ok": True, "detail": {"candidate": C1}},
        )
        g = gate.evaluate(SID, ev, changed=["src/a.py"], write_scope=["src"], screens=[], acceptance=1,
                          candidate=C1, review_blocking=[])
        self.assertIs(_check(g, "criteria have tests").outcome, Outcome.FAILED)


class TestSS04ResumeFeedbackReaderIsAlive(unittest.TestCase):
    """SS-04 — `_unfinished_review` reads `NOTE "review"`, a record nothing writes (verdicts are
    `reviewer:verdict`); a resumed story never receives the reviewer's rejection. Invariant E/G."""

    @unittest.expectedFailure   # SS-04
    def test_a_recorded_rejection_at_head_is_handed_to_the_resumed_developer(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp); _git(repo, "init", "-q"); _git(repo, "config", "user.email", "t@t"); _git(repo, "config", "user.name", "t")
            (repo / "a.txt").write_text("a\n", encoding="utf-8"); _git(repo, "add", "-A"); _git(repo, "commit", "-qm", "c")
            head = _git(repo, "rev-parse", "HEAD")
            root = repo / "_bmad-output"; root.mkdir()
            EvidenceStore(root).record(SID, Event(kind=NOTE, name="reviewer:verdict", ok=False, detail={
                "candidate": head, "verdict": "block",
                "findings": [{"tag": "block", "file": "a.txt", "line": 1, "why": "missing null check"}]}))
            self.assertIn("null check", I._unfinished_review(root, SID, repo))


class TestSS05EscalationDemotionStaysInsideTheEpoch(unittest.TestCase):
    """SS-05 — `_no_escalation` demotes today's blockers because the same (file, behaviour) was advisory
    on ANY earlier candidate, across a contract change, and flips the verdict to pass. Invariant B/T."""

    @unittest.expectedFailure   # SS-05
    def test_an_advisory_from_a_previous_epoch_cannot_demote_a_blocker_into_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EvidenceStore(Path(tmp))
            store.record(SID, Event(kind=NOTE, name="story:contract", detail={"fingerprint": "epoch-1", "codes": {}}))
            store.record(SID, Event(kind=NOTE, name="reviewer:verdict", ok=True, detail={
                "candidate": C1, "verdict": "pass",
                "findings": [{"tag": "should fix", "file": "src/a.py", "behavior_id": "FR-1", "why": "style"}]}))
            store.record(SID, Event(kind=NOTE, name="story:contract", detail={"fingerprint": "epoch-2", "codes": {}}))
            store.record(SID, Event(kind=NOTE, name="gate:input", detail={"candidate": C2, "attempt": 1}))
            verdict = I.Verdict(verdict="block", findings=[{"tag": "block", "file": "src/a.py", "behavior_id": "FR-1", "why": "wrong"}])
            I._no_escalation(SID, store, verdict, role="reviewer")
            self.assertEqual(verdict.verdict, "block", "a new epoch is a new contract; yesterday's advisory says nothing about it")


# ---------------------------------------------------------------- FAM-RETRY / INV-G, INV-F

class _ReviewBudgetCut(ScriptedClient):
    def run(self, spec):
        if spec.prompt.lstrip().startswith("# Review") and not spec.prompt.lstrip().startswith("# Security review"):
            raise BudgetExceeded("cap reached")
        return super().run(spec)


class TestSS12BudgetRejectionInReviewDoesNotCrash(ImplementTestCase):
    """SS-12 — `_review_session` handles BudgetExceeded with `from .mockup import RunResult`, a name that
    module does not define: the whole sprint dies with ImportError. Invariant G/F (typed outcome)."""

    @unittest.expectedFailure   # SS-12
    def test_review_budget_rejection_is_a_typed_outcome_not_an_import_error(self):
        out = self.implement(_ReviewBudgetCut())
        self.assertIsNotNone(out)


class _SecurityCut(ScriptedClient):
    def run(self, spec):
        if spec.prompt.lstrip().startswith("# Security review"):
            self.calls.append("security")
            return RunResult(ok=False, error="exceeded 10s", cost_usd=0.1)
        return super().run(spec)


class TestSS13SecurityExecutionFailureIsNotAVerdict(ImplementTestCase):
    """SS-13 — a security SESSION failure becomes `Check("security", FAILED)` and is cached as a verdict at
    the candidate; the loop reopens the developer (D-032's shape, security stage). Invariant G/F."""

    @unittest.expectedFailure   # SS-13a
    def test_gate_scores_a_security_execution_failure_as_unrunnable(self):
        ev = _ev({"kind": TOOL_RUN, "name": "test", "ok": True, "detail": {"candidate": C1}},
                 {"kind": TOOL_RUN, "name": "lint", "ok": True, "detail": {"candidate": C1}})
        g = gate.evaluate(SID, ev, changed=["src/a.py"], write_scope=["src"], screens=[], candidate=C1,
                          review_blocking=[], security=SecurityReport(error="could not run: exceeded 10s"))
        self.assertIs(_check(g, "security").outcome, Outcome.UNRUNNABLE)

    @unittest.expectedFailure   # SS-13b
    def test_a_cut_security_session_retries_security_not_the_developer(self):
        c = _SecurityCut()
        self.implement(c)
        self.assertEqual(c.develop_calls, 1, c.calls)


class TestSS14ToolEnvironmentFailureIsNotADeveloperAttempt(ImplementTestCase):
    """SS-14 — an UNRUNNABLE deterministic check (runner missing in the sandbox) blocks the gate and the
    loop's only move is a new developer session, charged to quality. Invariant G/N."""

    @unittest.expectedFailure   # SS-14
    def test_a_missing_test_runner_does_not_spend_developer_attempts(self):
        c = ScriptedClient()
        self.implement(c, config=self.config(**{"tools.test": "aisef-no-such-runner-xyz"}))
        self.assertEqual(c.develop_calls, 1, "the environment failed, not the developer")


class _ContextCut(ScriptedClient):
    def run(self, spec):
        r = super().run(spec)
        if self.calls[-1] == "develop":
            return RunResult(ok=False, error="prompt is too long: 210000 tokens > 200000 maximum", cost_usd=0.1)
        return r


class TestSS15EnvironmentExitStatusesAreNotQualityAttempts(ImplementTestCase):
    """SS-15 — `context`, `permission`, `cost` exit statuses leave the tree untouched and are charged to the
    developer's quality budget (D-006's shape). Invariant G."""

    @unittest.expectedFailure   # SS-15
    def test_a_context_window_exit_is_infra_not_quality(self):
        self.assertEqual(exit_status_of(RunResult(ok=False, error="prompt is too long: 210000 tokens")), "context")
        out = self.implement(_ContextCut())
        self.assertTrue(out.attempts[0].infra, out.attempts[0].error)


class TestSS17MergeDirtCheckHonoursOwnership(unittest.TestCase):
    """SS-17 — `merge_story` refuses a passed candidate when raw `git status` is non-empty, including the
    harness's own tool artifacts (`.coverage`) and copied client config. Invariant I."""

    @unittest.expectedFailure   # SS-17
    def test_a_tool_artifact_in_the_worktree_does_not_block_the_merge_of_the_frozen_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp); _git(repo, "init", "-q", "-b", "main"); _git(repo, "config", "user.email", "t@t"); _git(repo, "config", "user.name", "t")
            (repo / "goc.txt").write_text("g\n", encoding="utf-8"); _git(repo, "add", "-A"); _git(repo, "commit", "-qm", "goc")
            wm = WorktreeManager(repo)
            wt = wm.create(SID).path
            (wt / "src").mkdir(); (wt / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
            commit_paths(wt, "candidate", paths=["src"])
            cand = _git(wt, "rev-parse", "HEAD")
            (wt / ".coverage").write_bytes(b"\x00")          # written by the test tool, not the story
            res = wm.merge_story(SID, expected_candidate=cand)
            self.assertTrue(res.merged, res.message)


class TestSS18TransientBaselineFailureIsNotPermanent(unittest.TestCase):
    """SS-18 — a baseline recorded `unrunnable` (tool briefly missing) is never reused, and once the story
    has commits `head != root` records BASELINE_UNAVAILABLE forever. Invariant C/N: the root is known,
    the baseline can be captured there."""

    @unittest.expectedFailure   # SS-18
    def test_the_baseline_is_recaptured_at_the_known_root_once_the_tool_is_back(self):
        from aisef.harness.tools import BASELINE_RUN
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp); _git(repo, "init", "-q"); _git(repo, "config", "user.email", "t@t"); _git(repo, "config", "user.name", "t")
            (repo / "src").mkdir(); (repo / "src" / "a.py").write_text("x = 1\n", encoding="utf-8"); _git(repo, "add", "-A"); _git(repo, "commit", "-qm", "entry")
            root_sha = _git(repo, "rev-parse", "HEAD"); art = repo / "_bmad-output"; art.mkdir()
            story = Story(id=SID, epic_id="E", title="t", acceptance_criteria=["a"], covers=["FR-1"], write_scope=["src"])
            broken = Config({**DEFAULTS, "tools.test": "aisef-no-such-runner-xyz", "tools.lint": "true", "sandbox.use_docker": False})
            I.run_baseline(story, workdir=repo, artifact_root=art, config=broken, base_ref=root_sha)
            (repo / "src" / "b.py").write_text("y = 2\n", encoding="utf-8"); _git(repo, "add", "-A"); _git(repo, "commit", "-qm", "story work")
            fixed = Config({**DEFAULTS, "tools.test": "true", "tools.lint": "true", "sandbox.use_docker": False})
            I.run_baseline(story, workdir=repo, artifact_root=art, config=fixed, base_ref=root_sha)
            recs = list(EvidenceStore(art).read(SID).of(TOOL_RUN, BASELINE_RUN))
            self.assertTrue(any(not r.detail.get("unrunnable") and r.detail.get("root") == root_sha for r in recs),
                            [r.detail.get("unrunnable") for r in recs])


# ---------------------------------------------------------------- FAM-PROSE / INV-F

class TestSS23RedTestsAreNotAMissingTool(unittest.TestCase):
    """SS-23 — `unrunnable_reason` treats the bare substring "not found" anywhere in runner output as a
    missing tool when no test PASSED; an all-red suite whose assertions say "not found" becomes
    TOOL_UNRUNNABLE. Invariant F: failed_ids already prove the runner ran."""

    @unittest.expectedFailure   # SS-23
    def test_an_all_red_suite_mentioning_not_found_is_a_test_failure(self):
        out = ("tests/test_a.py::test_lookup FAILED\n"
               "tests/test_a.py::test_other FAILED\n"
               "E   AssertionError: user not found\n"
               "E   AssertionError: element not found\n"
               "2 failed in 0.10s\n")
        self.assertEqual(unrunnable_reason("test", 1, out), "")


class TestSS24ProseNeverOverridesAStructuredVerdict(unittest.TestCase):
    """SS-24 — `_reconcile` unions text-derived `[block]` items with the JSON verdict; a prose line blocks a
    candidate whose structured verdict is `pass` with no findings. Invariant F."""

    @unittest.expectedFailure   # SS-24
    def test_a_prose_block_line_does_not_block_when_the_structured_verdict_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EvidenceStore(Path(tmp))
            text = ("Earlier I noted:\n- [block] src/a.py:10 — was missing a null check (now fixed)\n\n"
                    "```json\n{\"verdict\": \"pass\", \"findings\": []}\n```\n")
            verdict = I.review_verdict(text)
            self.assertEqual(verdict.verdict, "pass")
            self.assertEqual(I._reconcile(SID, store, text, verdict, role="reviewer"), [])


class TestSS25ScopeVerdictComesFromFindingsNotProse(unittest.TestCase):
    """SS-25 — `_paths_outside` regexes any `word.ext` token out of reviewer prose to decide that a repeated
    complaint points OUTSIDE the write scope, which makes the story terminally stuck. Invariant F/Q."""

    @unittest.expectedFailure   # SS-25
    def test_a_technology_name_in_prose_is_not_a_path_outside_scope(self):
        self.assertEqual(I._paths_outside(["[block] src/list.ts:4 — follow the Node.js convention here"], ["src"]), [])


class TestSS26EnvironmentFailureIsNotErasedBySubstring(unittest.TestCase):
    """SS-26 — `_vang_ma_cua_story` clears an environment failure when a changed file's stem appears anywhere
    in the traceback; the nop then scores as correctly red and TDD passes on a suite that never ran.
    Invariant F/N/T."""

    @unittest.expectedFailure   # SS-26
    def test_a_third_party_import_error_stays_an_environment_failure(self):
        res = SimpleNamespace(
            unrunnable=f"{NO_SETUP} — dependencies missing",
            output=lambda: ('Traceback (most recent call last):\n  File "/w/src/config.py", line 3, in <module>\n'
                            "    import requests\nModuleNotFoundError: No module named 'requests'\n", ""))
        self.assertEqual(I._vang_ma_cua_story(res, ["src/config.py"]), "")


class TestSS27NoiseFilterHasASeverityFloor(unittest.TestCase):
    """SS-27 — `is_noise` drops a finding of ANY severity whose body mentions rate limiting or throttling;
    a critical auth-bypass finding worded with "no rate limit" stops blocking. Invariant F/T."""

    @unittest.expectedFailure   # SS-27
    def test_a_critical_finding_mentioning_rate_limits_still_blocks(self):
        rep = parse_security("[critical] auth bypass: the login endpoint has no rate limit, so credential stuffing succeeds\n")
        self.assertTrue(rep.blocking(("critical", "high")), (rep.findings, getattr(rep, "filtered", None)))


class TestSS28ExitStatusReadsTheProviderNotTheAgentsProse(unittest.TestCase):
    """SS-28 — `exit_status_of` classifies `auth` from substrings of the agent's own final text; a story
    about 401 handling ends as a fatal credential rejection. Invariant F."""

    @unittest.expectedFailure   # SS-28
    def test_a_final_message_about_401_handling_is_not_an_auth_failure(self):
        res = RunResult(ok=False, error="process exited 1 without a result event",
                        raw_result={"result": "I implemented the 401 Unauthorized handler for invalid API key requests."})
        self.assertNotEqual(exit_status_of(res), "auth")


class TestSS30PlaceholderRegexDoesNotBlockTodoApps(unittest.TestCase):
    """SS-30 — the stories machine gate rejects criteria matching `\\bTODO\\b`; every to-do application
    (this framework's own dogfood corpora) fails plan approval. Invariant F."""

    @unittest.expectedFailure   # SS-30
    def test_a_criterion_about_todo_items_is_not_a_placeholder(self):
        self.assertIsNone(_GIU_CHO.search("a TODO item can be marked done"))


# ---------------------------------------------------------------- FAM-OWNERSHIP / INV-I, INV-K

class TestSS35RenamedPathsKeepTheirIdentity(unittest.TestCase):
    """SS-35 — `changed_files` slices `entry[3:]` off every NUL field of `git status --porcelain -z`; a
    staged rename emits the original path as a bare field and becomes a phantom `/…` path outside every
    scope. Invariant I/J."""

    @unittest.expectedFailure   # SS-35
    def test_a_staged_rename_yields_real_paths_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp); _git(repo, "init", "-q"); _git(repo, "config", "user.email", "t@t"); _git(repo, "config", "user.name", "t")
            (repo / "src").mkdir(); (repo / "src" / "a.py").write_text("x = 1\n", encoding="utf-8"); _git(repo, "add", "-A"); _git(repo, "commit", "-qm", "c")
            _git(repo, "mv", "src/a.py", "src/b.py")
            paths = changed_files(str(repo))
            self.assertTrue(paths and all(p.startswith("src/") for p in paths), paths)


class _ReviewerRunsCoverage(ScriptedClient):
    def run(self, spec):
        r = super().run(spec)
        dau = spec.prompt.lstrip().splitlines()[0]
        if dau.startswith("# Review") and not dau.startswith("# Security review"):
            (Path(spec.workdir) / ".coverage").write_bytes(b"\x00")   # pytest-cov, run to check a claim
        return r


class TestSS36ToolArtifactsAreNotReviewerWrites(ImplementTestCase):
    """SS-36 — `_tree_snapshot` skips harness-owned paths but not tool artifacts, so a reviewer that runs
    the suite (allowed, expected) and leaves `.coverage` is scored as having modified the tree: review
    discarded, REVIEW_UNRUNNABLE after the retry budget. Invariant I."""

    @unittest.expectedFailure   # SS-36
    def test_a_reviewer_that_only_ran_the_tests_is_not_a_tree_mutation(self):
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.project, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.project, check=True)
        out = self.implement(_ReviewerRunsCoverage())
        ev = EvidenceStore(self.artifacts).read(self.story.id)
        self.assertFalse(any(e.name == "review:immutable" for e in ev.events))
        self.assertTrue(out.done, out.summary())


class TestSS39VendorPathsShareOneOwnershipRule(HygieneCase):
    """SS-39 — `changed_files` ignores vendor directories anywhere in a path (`node_modules` as a segment);
    `_tree_snapshot`/`_dirt_outside_scope` skip them only at the root. A nested `node_modules` the session
    installed is recorded as a violation and DELETED by retry hygiene. Invariant I/K (two rules, one truth)."""

    @unittest.expectedFailure   # SS-39
    def test_a_nested_vendor_directory_is_neither_a_violation_nor_deleted(self):
        def first(work):
            ledgerlock_pattern(work)
            p = work / "packages" / "web" / "node_modules" / "left-pad" / "index.js"
            p.parent.mkdir(parents=True); p.write_text("module.exports = 1\n", encoding="utf-8")
        c = Developer(first=first)
        self.implement(c)
        self.assertTrue((self.work / "packages" / "web" / "node_modules" / "left-pad" / "index.js").exists(),
                        "hygiene deleted a vendor tree the guard itself does not count as a write")
        for e in EvidenceStore(self.artifacts).read(self.story.id).of(NOTE, "write-scope:violation"):
            self.assertFalse(any("node_modules" in p for p in e.detail.get("untracked", [])), e.detail)


if __name__ == "__main__":
    unittest.main()
