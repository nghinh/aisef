"""Regression tests written from the LedgerLock dogfood evidence (2026-09-15,
AISEF 1.7.2 + OpenCode 1.18.29 on Windows 11, Docker Desktop, python:3.12-slim).

Evidence package: ledgerlock-dogfood-evidence/20260915-154214+0700 (run.log,
sprint-status.json, journal/, evidence/, reviews/, worktrees). Intake records:
closure-evidence/dogfood/ledgerlock/F-*.json.

RED tests are the defects, reproduced deterministically; they stay red until a
fix lands in a later release — the product is frozen at 1.7.2 while G6 is
open. The GREEN test is the recovery path the evidence made suspect and which
turned out to work.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.clients.base import RunSpec  # noqa: E402
from aisef.clients.opencode import OpenCodeAdapter  # noqa: E402
from aisef.clients.stream import exit_status_of  # noqa: E402
from aisef.control.journal import Entry, JournalStore, reconcile_all  # noqa: E402
from aisef.control.state import SprintState, StateStore, StoryRecord, StoryStatus  # noqa: E402
from aisef.harness import guardrails as G  # noqa: E402
from aisef.phases import implement as I  # noqa: E402


# ---------------------------------------------------------------- F-1 (A)


class TestStuckMentionIsNotAPlanVerdict(unittest.TestCase):
    """F-2 / D-026 — STORY-01-03 was declared "deadlock due to plan, reviewer
    verified: [stuck] doesn't apply." after ONE attempt and marked terminal
    ("retrying will not resolve this"). The reviewer's JSON verdict was `block`
    with three `block` findings and no stuck item; the words came from its
    reasoning prose — "The file IS there. So [stuck] doesn't apply." — where
    the tag was not in backticks, so the text parser split it out as an item
    and the union with the JSON made it the story's terminal verdict.

    Rule (1.7.3): a terminal plan deadlock rests on the structured verdict
    only. Prose still blocks (fail closed); it never terminates.
    """

    PROSE = "The file IS there. So [stuck] doesn't apply.\n\n"
    BLOCK_JSON = ('```json\n{"verdict": "block", "findings": [{"tag": "block", '
                  '"file": "src/ledgerlock/io.py", "line": 62, "why": "AD-3 mandates fsync"}]}\n```\n')
    STUCK_JSON = ('```json\n{"verdict": "stuck", "findings": [{"tag": "stuck", "file": "docs/ops.md", '
                  '"why": "AC-3 needs docs/ops.md, outside write_scope"}]}\n```\n')

    def test_a_prose_stuck_mention_beside_a_structured_block_verdict_is_not_a_plan_deadlock(self):
        verdict = I.review_verdict(self.PROSE + self.BLOCK_JSON)
        self.assertEqual(verdict.verdict, "block")
        self.assertEqual(I.structured_plan_defects(verdict), [])
        # the text parser may still read the sentence as a blocking item — that
        # is fail-closed, not terminal
        self.assertTrue(any(x.startswith("[block]") for x in verdict.blocking()))

    def test_a_structured_stuck_finding_still_is_a_plan_deadlock(self):
        got = I.structured_plan_defects(I.review_verdict(self.PROSE + self.STUCK_JSON))
        self.assertEqual(len(got), 1)
        self.assertIn("docs/ops.md", got[0])

    def test_a_stuck_verdict_without_findings_stays_fail_closed(self):
        got = I.structured_plan_defects(I.Verdict("stuck", []))
        self.assertEqual(len(got), 1, "a `stuck` verdict field is structured evidence, even with no items")

    def test_a_prose_only_review_never_terminates_a_story(self):
        """No JSON after the schema reminder: malformed structured output.
        The text items block the attempt; nothing here is terminal."""
        self.assertEqual(I.structured_plan_defects(None), [])
        self.assertEqual(I.blocking_findings("- [stuck] AC-3 needs `docs/ops.md`, outside write_scope\n"),
                         ["[stuck] AC-3 needs `docs/ops.md`, outside write_scope"])


# ---------------------------------------------------------------- F-2 (B)


#: A grandchild that streams `step_finish` for 4 s. On the dogfood machine the
#: direct child was `opencode.CMD` (a cmd.exe shim) and node was the grandchild.
_GRANDCHILD = (
    "import json, time\n"
    "for i in range(40):\n"
    "    print(json.dumps({'type': 'step_finish', 'part': {'tokens': {'input': 1}}})"
    ".replace(chr(39), chr(34)), flush=True)\n"
    "    time.sleep(0.1)\n"
)
#: The launcher: spawns the grandchild and waits — exactly what a `.cmd`/`sh`
#: wrapper without `exec` does.
_LAUNCHER = (
    "import subprocess, sys\n"
    f"subprocess.run([sys.executable, '-c', {_GRANDCHILD!r}])\n"
)


class _ViaLauncher(OpenCodeAdapter):
    def available(self) -> bool:
        return True

    def build_command(self, spec):
        return [sys.executable, "-c", _LAUNCHER]


class _Direct(_ViaLauncher):
    def build_command(self, spec):
        return [sys.executable, "-c", _GRANDCHILD]


class TestTurnCapKillsTheWholeProcessTree(unittest.TestCase):
    """F-2 — five developer sessions ran 75, 108, 179, 186 and 142 turns against
    `run.max_turns = 40`. The adapter counts `step_finish` and calls
    `proc.kill()` on the direct child; the child was the npm shim
    `opencode.CMD`, node survived, kept writing to the inherited pipe, and the
    adapter counted on until EOF. The label ("max_turns … cap 40") was honest;
    the cap was not enforced.
    """

    def test_the_cap_stops_a_direct_child(self):
        """Control: the same stream as a direct child is stopped at the cap."""
        res = _Direct().run(RunSpec(prompt="x", workdir=".", max_turns=5, timeout_seconds=60))
        self.assertEqual(exit_status_of(res), "max_turns")
        self.assertLessEqual(res.num_turns, 5 + 2)

    def test_the_cap_stops_a_session_whose_client_is_a_grandchild(self):
        t0 = time.monotonic()
        res = _ViaLauncher().run(RunSpec(prompt="x", workdir=".", max_turns=5, timeout_seconds=60))
        took = time.monotonic() - t0
        self.assertEqual(exit_status_of(res), "max_turns")
        self.assertLessEqual(res.num_turns, 5 + 2, f"ran {res.num_turns} turns against a cap of 5")
        self.assertLess(took, 2.5, f"took {took:.1f}s — the grandchild kept streaming after the kill")


# ---------------------------------------------------------------- F-4 (C1)


class TestDeclaredToolsLiveInTheDeclaredImage(unittest.TestCase):
    """F-4 / D-028 — the python preset paired `python -m pytest` and `ruff
    check .` with `python:3.12-slim`, which carries neither; every tool call
    is a fresh `docker run --rm`; `aisef doctor` called the image "(matches
    stack)". Now the preset names an image the harness builds from a pinned
    recipe, and every declared tool is probed where it will run before a
    session is paid for.
    """

    def test_the_python_preset_declares_a_harness_built_pinned_image(self):
        from aisef.cli.harness import STACK_PRESETS
        from aisef.harness import verify_image as V
        image = str(STACK_PRESETS["python"]["sandbox.image"])
        recipe = V.recipe_for(image)
        self.assertIsNotNone(recipe, image)
        self.assertIn("@sha256:", recipe.base, "the base is pinned by digest, not by tag")
        self.assertTrue(any(p.startswith("pytest==") for p in recipe.packages))
        self.assertTrue(any(p.startswith("ruff==") for p in recipe.packages))
        self.assertEqual(image, recipe.name)
        self.assertIn(recipe.digest[:12], image, "the name carries the recipe's digest")

    def test_probes_are_derived_from_the_declared_commands(self):
        from aisef.harness import verify_image as V
        self.assertEqual(V.probe_command("python -m pytest -v"), ["python", "-c", "import pytest"])
        self.assertEqual(V.probe_command("ruff check . --exclude .claude"), ["sh", "-c", "command -v ruff"])
        self.assertEqual(V.probe_command("go test -v ./..."), ["sh", "-c", "command -v go"])
        self.assertIsNone(V.probe_command("npx vitest run"), "project-local runner: not the image's to provide")

    def _project(self, d, image):
        root = Path(d)
        (root / "pyproject.toml").write_text("", encoding="utf-8")
        (root / ".ai").mkdir()
        (root / ".ai" / "config.json").write_text(json.dumps({
            "tools.test": "python -m pytest -v", "tools.lint": "ruff check .",
            "sandbox.image": image, "sandbox.provider": "aisef.harness.sandbox:FakeProvider"}),
            encoding="utf-8")
        return root

    def test_a_declared_tool_missing_from_the_sandbox_fails_the_check(self):
        from unittest import mock

        from aisef.config import Config
        from aisef.harness import sandbox as SB
        from aisef.harness import verify_image as V

        def probe(spec):
            # pytest present, ruff absent — the LedgerLock image at 14:54:58
            ok = "import pytest" in " ".join(spec.cmd)
            return SB.SandboxResult(0 if ok else 127, stderr="" if ok else "sh: ruff: not found")

        with tempfile.TemporaryDirectory() as d:
            root = self._project(d, "some/ci-image:1")
            with mock.patch.object(SB, "run", side_effect=probe):
                checks = V.check_tools(root, Config.load(root), build=False)
        by_key = {c.key: c for c in checks}
        self.assertTrue(by_key["tools.test"].ok)
        self.assertFalse(by_key["tools.lint"].ok)
        self.assertIn("MISSING in some/ci-image:1", by_key["tools.lint"].line)

    def test_run_refuses_to_start_when_a_declared_tool_is_missing(self):
        from unittest import mock

        from aisef.config import Config
        from aisef.harness import sandbox as SB
        from aisef.phases.run import _missing_tools

        with tempfile.TemporaryDirectory() as d:
            root = self._project(d, "some/ci-image:1")
            with mock.patch.object(SB, "run", return_value=SB.SandboxResult(127, stderr="not found")):
                missing = _missing_tools(root, Config.load(root))
            self.assertEqual(len(missing), 2, missing)
            with mock.patch.object(SB, "run", return_value=SB.SandboxResult(0)):
                self.assertEqual(_missing_tools(root, Config.load(root)), [])

    def test_no_declared_image_means_no_run_preflight(self):
        """The preflight guards a *declared* environment; fixtures with the
        provider's default image are the doctor's business, not the run's."""
        from aisef.config import DEFAULTS, Config
        from aisef.phases.run import _missing_tools
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_missing_tools(Path(d), Config({**DEFAULTS, "tools.test": "nonexistent-tool"})), [])

    def test_doctor_reports_the_missing_tool(self):
        from unittest import mock

        from aisef.cli import main
        from aisef.harness import sandbox as SB

        with tempfile.TemporaryDirectory() as d:
            root = self._project(d, "some/ci-image:1")
            (root / "docs").mkdir(); (root / "docs" / "requirements.md").write_text("# r\n", encoding="utf-8")
            buf = io.StringIO()
            with (mock.patch.object(SB, "run", return_value=SB.SandboxResult(127, stderr="sh: ruff: not found")),
                  redirect_stdout(buf)):
                code = main(["--project", str(root), "doctor"])
            out = buf.getvalue()
            self.assertIn("MISSING in some/ci-image:1", out)
            self.assertNotEqual(code, 0, "a missing declared tool is not 'ready'")


# ---------------------------------------------------------------- F-3 (C2)


class TestMissingTestRunnerIsUnrunnableNotRed(unittest.TestCase):
    """F-5 / D-029 — `python:3.12-slim` has no pytest; every `aisef tool test`
    printed `/usr/local/bin/python: No module named pytest`, exit 1, and the
    gate read it as "the most recent test run is still failing". Three agents
    spent their sessions on a red test that never ran. `ruff` (exit 127) was
    classified correctly; the missing *module* was not.
    """

    LAUNCHER = "/usr/local/bin/python: No module named pytest"

    def _res(self, name, code, out):
        from aisef.harness.tools import ToolResult, unrunnable_reason
        r = ToolResult(name=name, ok=code == 0, exit_code=code, stdout=out)
        r.unrunnable = unrunnable_reason(name, code, out)
        return r

    def test_no_module_named_the_runner_is_unrunnable(self):
        from aisef.harness.tools import TOOL_UNRUNNABLE, outcome_kind
        r = self._res("test", 1, self.LAUNCHER)
        self.assertTrue(r.unrunnable, "a missing test runner is 'could not run', not 'tests are red'")
        self.assertEqual(outcome_kind(r), TOOL_UNRUNNABLE)

    def test_a_missing_project_dependency_is_an_environment_failure(self):
        from aisef.harness.tools import ENVIRONMENT_FAILURE, outcome_kind
        r = self._res("test", 1, "ImportError while importing test module 'tests/test_x.py'\n"
                                 "ModuleNotFoundError: No module named 'requests'")
        self.assertEqual(outcome_kind(r), ENVIRONMENT_FAILURE)

    def test_a_red_test_that_mentions_a_module_is_still_a_red_test(self):
        """Control: pytest ran, one test passed, one failed on an import — that
        is behavioural evidence and stays TEST_FAILED."""
        from aisef.harness.tools import TEST_FAILED, outcome_kind
        r = self._res("test", 1, "tests/a.py::test_ok PASSED\ntests/a.py::test_x FAILED\n"
                                 "E   ModuleNotFoundError: No module named 'foo'")
        self.assertEqual(r.unrunnable, "")
        self.assertEqual(outcome_kind(r), TEST_FAILED)

    def test_the_lint_tool_missing_is_still_classified_as_before(self):
        from aisef.harness.tools import TOOL_UNRUNNABLE, outcome_kind
        r = self._res("lint", 127, 'exec: "ruff": executable file not found in $PATH')
        self.assertEqual(outcome_kind(r), TOOL_UNRUNNABLE)

    def test_the_completion_guard_does_not_call_an_unrun_suite_red(self):
        """The gate message the agents saw. With `unrunnable` set the guard
        lets the session stop with the right reason instead of "still failing"."""
        from aisef.harness.guardrails import check_completion
        from aisef.harness.observe import TOOL_RUN, Event

        class _Ev:
            def __init__(self, detail):
                self._e = Event(kind=TOOL_RUN, name="test", ok=False, detail=detail)

            def last(self, kind, name):
                return self._e if (kind, name) == (TOOL_RUN, "test") else None

            def stale_since_last_test(self):
                return []

            def of(self, *a):
                return [self._e]

        r = self._res("test", 1, self.LAUNCHER)
        v = check_completion(_Ev({"unrunnable": r.unrunnable, "tail": self.LAUNCHER}))
        self.assertTrue(v.allowed, v.reason)


# ---------------------------------------------------------------- F-4 (D)


class TestCoverageDataFileIsNotAStoryChange(unittest.TestCase):
    """F-4 — `tools.test` ran with `--cov`; pytest-cov wrote `.coverage` at the
    worktree root; the `diff-scope` guard then blocked every bash call with
    "1 files changed outside write_scope: .coverage" (20 blocks in six minutes
    on STORY-01-03). A file the harness's own tool writes is not the agent's
    change. `VENDOR_PATHS` lists the `coverage/` directory but not the data file.
    """

    def test_a_coverage_data_file_written_by_the_test_tool_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subprocess.run(["git", "-C", d, "init", "-q"], check=True)
            subprocess.run(["git", "-C", d, "config", "user.email", "t@t.t"], check=True)
            subprocess.run(["git", "-C", d, "config", "user.name", "t"], check=True)
            (root / "src").mkdir()
            (root / "src" / "x.py").write_text("x = 1\n", encoding="utf-8")
            subprocess.run(["git", "-C", d, "add", "."], check=True)
            subprocess.run(["git", "-C", d, "commit", "-qm", "base"], check=True)
            (root / ".coverage").write_bytes(b"SQLite format 3\x00")
            (root / "src" / "x.py").write_text("x = 2\n", encoding="utf-8")
            changed = G.changed_files(d)
            self.assertNotIn(".coverage", changed, changed)
            self.assertTrue(G.check_diff_scope(changed, ["src/x.py"]).ok)


# --------------------------------------------- orphaned running state (GREEN)


class TestOrphanedRunningClaimIsReclaimedOnTheNextRun(unittest.TestCase):
    """The priority finding. After the orchestrator died mid-wave, STORY-01-01
    and STORY-01-02 stayed `running` with `claimed_by = HOST:PID` of a dead
    process; their journals ended at `candidate.frozen` with no
    `attempt.aborted` — the process was killed, not unwound. This test rebuilds
    that exact shape and runs what the next `aisef run` runs first. It is
    GREEN: recovery works; what the evidence exposed is that nothing *else*
    (`aisef status`) says the claim is dead — see the test below.
    """

    def _orphaned(self, root: Path, sid: str) -> None:
        j = JournalStore(root)
        for step, data in (("attempt.started", {}), ("worktree.created", {"path": "wt"}),
                           ("status.running", {}), ("changes.detected", {"count": 7}),
                           ("candidate.frozen", {"sha": "52664fa60a8cdea09922d2d563393ace8d02ef2e"})):
            j.record(sid, Entry(step=step, attempt=1, data=data))

    def test_reconcile_all_resets_the_dead_claims_and_the_stories_can_be_claimed_again(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            st = StateStore(root)
            st.save(SprintState(stories={
                sid: StoryRecord(id=sid, epic_id="EPIC-01", status="running", claimed_by="EDU-BGD-1143:36316")
                for sid in ("STORY-01-01", "STORY-01-02")}))
            for sid in ("STORY-01-01", "STORY-01-02"):
                self._orphaned(root, sid)
            out = reconcile_all(artifact_root=root, state=st, worktrees=None)
            self.assertEqual(sorted(r.story_id for r in out), ["STORY-01-01", "STORY-01-02"])
            self.assertTrue(all(r.action == "undo" for r in out))
            for sid in ("STORY-01-01", "STORY-01-02"):
                rec = st.load().stories[sid]
                self.assertIs(rec.state, StoryStatus.PENDING)
                self.assertEqual(rec.claimed_by, "")
                self.assertTrue(st.claim(sid))


class TestStatusNamesADeadClaim(unittest.TestCase):
    """F-5 — the observability half of the priority finding. Thirty-six minutes
    after the last orchestrator line, `aisef status` still printed `running 2`
    with no hint that `claimed_by` named a process that no longer existed.
    `running` from a live process and `running` from a dead one are different
    facts; the record carries `HOST:PID`, so on the same host the difference is
    knowable.
    """

    def test_status_says_when_the_claiming_process_is_gone(self):
        import socket
        from aisef.cli import main

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "docs").mkdir()
            (root / "docs" / "requirements.md").write_text("# r\n", encoding="utf-8")
            art = root / "_bmad-output"
            art.mkdir()
            (art / "stories.index.json").write_text(json.dumps({
                "stories": [{"id": "STORY-01-01", "epic_id": "EPIC-01"}],
                "epics": [{"id": "EPIC-01"}], "waves": {"EPIC-01": [["STORY-01-01"]]}}), encoding="utf-8")
            dead = f"{socket.gethostname()}:{2**22 - 7}"
            StateStore(art).save(SprintState(stories={
                "STORY-01-01": StoryRecord(id="STORY-01-01", epic_id="EPIC-01", status="running", claimed_by=dead)}))
            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["--project", str(root), "status"])
            text = buf.getvalue().lower()
            self.assertIn("running", text)
            self.assertTrue(any(w in text for w in ("orphan", "no such process", "dead", "not running")),
                            f"status must say the claim is dead:\n{buf.getvalue()}")


if __name__ == "__main__":
    unittest.main()
