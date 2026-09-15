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
from aisef.harness.tools import unrunnable_reason  # noqa: E402
from aisef.phases import implement as I  # noqa: E402


# ---------------------------------------------------------------- F-1 (A)


class TestStuckMentionIsNotAPlanVerdict(unittest.TestCase):
    """F-1 — STORY-01-03 was declared "deadlock due to plan, reviewer verified:
    [stuck] doesn't apply." after ONE attempt and marked terminal ("retrying
    will not resolve this"). The reviewer's JSON verdict was `block` with three
    `block` findings and no stuck item; the words came from its reasoning
    prose — "The file IS there. So [stuck] doesn't apply." — where the tag was
    not in backticks, so `_TAG_MO_DAU` split it out as an item and `_la_muc_that`
    exempted `[stuck]` from needing a path. A mention that negates the tag became
    the story's terminal verdict.
    """

    SENTENCE = "The file IS there. So [stuck] doesn't apply."

    def test_a_negated_prose_mention_of_the_stuck_tag_is_not_an_item(self):
        self.assertEqual(I.blocking_findings(self.SENTENCE), [])

    def test_a_stuck_item_that_names_no_criterion_or_path_is_not_a_plan_defect(self):
        items = I.blocking_findings("- [stuck] doesn't apply.\n")
        self.assertEqual(I.plan_defects(items), [],
                         "a stuck verdict must name what cannot be met from inside the story")

    def test_a_real_stuck_item_still_counts(self):
        """Negative control: the shape the prompt asks for keeps working."""
        text = "- [stuck] AC-STORY-01-03-3 requires writing `docs/ops.md`, which is outside write_scope\n"
        self.assertEqual(len(I.plan_defects(I.blocking_findings(text))), 1)


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


# ---------------------------------------------------------------- F-3 (C2)


class TestMissingTestRunnerIsUnrunnableNotRed(unittest.TestCase):
    """F-3 — `python:3.12-slim` has no pytest; every `aisef tool test` printed
    `/usr/local/bin/python: No module named pytest`, exit 1, and the gate read
    it as "the most recent test run is still failing". Three agents spent their
    sessions on a red test that never ran. `ruff` (exit 127) was classified
    correctly; the missing *module* was not.
    """

    def test_no_module_named_the_runner_is_unrunnable(self):
        why = unrunnable_reason("test", 1, "/usr/local/bin/python: No module named pytest")
        self.assertTrue(why, "a missing test runner is 'could not run', not 'tests are red'")


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
