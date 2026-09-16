"""Retry hygiene after developer out-of-scope mutations (D-034, lỗi 188 — OBS-OC-3).

Measured on aisef 1.7.5 (public wheel, LedgerLock OpenCode replay, STORY-04-01, 2026-09-16, after the
AC-4 arbitration): the developer session of attempt 1 ran `ruff format ledgerlock/ …`, which reformatted
`ledgerlock/ledger.py` and `ledgerlock/store.py` — cosmetic, outside the write scope. `freeze_candidate`
commits only in-scope paths (de2d3244 = cli.py + the story test), so the two files stayed modified in the
worktree; the gate failed `write scope` (correct). Nothing restored them before the retry: attempts 2 and 3
opened on the same dirty tree, the OpenCode `diff-scope` after-hook threw on every Bash/Write/Edit call
(`ls -la`, `echo hello`, `/bin/true` …), the developer could neither act nor revert (`git checkout --` and
`git reset --hard` are blocked, Write/Edit on the two files is outside scope), and both sessions ended at
the 80-turn cap with `moved_tree: false` — 160 turns, nothing graded.

Owner invariant (2026-09-16): a new developer retry starts from a clean, valid candidate state; a failed
attempt's out-of-scope mutations never poison later attempts. Detect and record the violating paths;
the freeze keeps only in-scope changes; before the next attempt restore tracked violating paths from the
frozen candidate and remove only the violating untracked ones, keep every in-scope change, record exactly
what was done, verify the tree is clean of out-of-scope violations, and only then launch the developer.
The model is never responsible for discovering a recovery command.

No OpenCode here: the scripted developer does what the real one did, and the assertion surface is the
tree exactly as the **next** developer session finds it (`Developer.seen`).
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tests  # noqa: E402,F401 — HostProvider in place of docker (tests/__init__.py)

from aisef.clients.base import Capability, ClientAdapter, RunSpec, Support  # noqa: E402
from aisef.clients.stream import RunResult  # noqa: E402
from aisef.config import DEFAULTS, Config  # noqa: E402
from aisef.control.normalize import Story  # noqa: E402
from aisef.harness.guardrails import ENV_BASE_REF, changed_files, check_diff_scope, scope_from_env  # noqa: E402
from aisef.harness.observe import NOTE, EvidenceStore  # noqa: E402
from aisef.phases.implement import implement_story  # noqa: E402

SID = "STORY-04-01"
SCOPE = ["ledgerlock/cli.py", "tests/test_cli_exit_codes.py"]
CLI = "def main(argv=None):\n    return 0\n"
LEDGER = ('def repair_tail(lines):\n'
          '    return {"ok": False, "first_bad_index": len(lines) - 1, "reason": "unterminated"}\n')
STORE = "def write_atomic(path, data):\n    path.write_bytes(data)"      # no trailing newline: what a formatter adds
FORMAT = "def normalize(s):\n    return s\n"
VIOLATION = "write-scope:violation"
RECOVERY = "retry:recovery"


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout.strip()


def ledgerlock_pattern(work: Path) -> None:
    """What the real session did: an in-scope change and a formatter pass over the whole package.
    (The story test file stays in the declared scope but is not written here: with `tools.test = true`
    a test file would trip the TDD and nop checks, which are not what this file measures.)"""
    (work / "ledgerlock" / "cli.py").write_text(CLI + "\n\ndef repair(argv):\n    return 0\n", encoding="utf-8")
    (work / "ledgerlock" / "ledger.py").write_text(
        LEDGER.replace('return {"ok"', 'return {\n        "ok"'), encoding="utf-8")   # reformatted dict
    (work / "ledgerlock" / "store.py").write_text(STORE + "\n", encoding="utf-8")   # trailing newline added


def in_scope_fix(work: Path) -> None:
    (work / "ledgerlock" / "cli.py").write_text(CLI + "\n\ndef repair(argv):\n    return 2\n", encoding="utf-8")


def _read(work: Path, rel: str):
    p = work / rel
    return p.read_text(encoding="utf-8") if p.exists() else None


def _snapshot(work: Path, env: dict) -> dict:
    """The tree as a developer session finds it — including the verdict the `diff-scope`
    after-hook would compute for its very first Bash call (same function, same inputs)."""
    v = check_diff_scope(changed_files(str(work), base_ref=env.get(ENV_BASE_REF, "")), scope_from_env(env))
    return {
        "ledger": _read(work, "ledgerlock/ledger.py"), "store": _read(work, "ledgerlock/store.py"),
        "format": _read(work, "ledgerlock/format.py"), "cli": _read(work, "ledgerlock/cli.py"),
        "scratch": (work / "ledgerlock" / "scratch_notes.py").exists(),
        "status": _git(work, "status", "--porcelain", "-uall"),
        "staged": _git(work, "diff", "--cached", "--name-only"),
        "head": _git(work, "rev-parse", "HEAD"),
        "guard_allowed": v.allowed, "guard_reason": v.reason,
    }


class Developer(ClientAdapter):
    """Scripted agent: `first` runs in developer session 1, `then` in every later one; what each later
    session finds in the tree is recorded in `seen`. Reviewer and security answer clean unless told otherwise."""

    id = "scripted"

    def __init__(self, first=ledgerlock_pattern, then=in_scope_fix, *, reviewer_writes=None):
        self.first, self.then, self.reviewer_writes = first, then, reviewer_writes
        self.seen: list[dict] = []
        self.develop_calls = 0

    def available(self) -> bool:
        return True

    def capabilities(self):
        return {c: Support.NATIVE for c in Capability}

    def run(self, spec: RunSpec) -> RunResult:
        dau = spec.prompt.lstrip().splitlines()[0] if spec.prompt.strip() else ""
        if dau.startswith("# Security review"):
            return RunResult(ok=True, text="không có phát hiện bảo mật", cost_usd=0.1)
        if dau.startswith("# Review"):
            if self.reviewer_writes:
                self.reviewer_writes(Path(spec.workdir))
            return RunResult(ok=True, text="không có mục chặn", cost_usd=0.1)
        work = Path(spec.workdir)
        self.develop_calls += 1
        if self.develop_calls == 1:
            self.first(work)
        else:
            self.seen.append(_snapshot(work, dict(spec.env)))
            if self.then:
                self.then(work)
        return RunResult(ok=True, text="xong", cost_usd=1.0)


class HygieneCase(unittest.TestCase):
    """A real project, a real story worktree, the LedgerLock layout: cli.py and the story test in scope,
    ledger.py / store.py / format.py outside it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        _git(self.project, "init", "-q")
        _git(self.project, "config", "user.email", "t@t")
        _git(self.project, "config", "user.name", "t")
        pkg = self.project / "ledgerlock"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "cli.py").write_text(CLI, encoding="utf-8")
        (pkg / "ledger.py").write_text(LEDGER, encoding="utf-8")
        (pkg / "store.py").write_text(STORE, encoding="utf-8")
        (pkg / "format.py").write_text(FORMAT, encoding="utf-8")
        (self.project / ".gitignore").write_text(".venv/\n", encoding="utf-8")
        _git(self.project, "add", "-A")
        _git(self.project, "commit", "-qm", "entry")
        self.entry = _git(self.project, "rev-parse", "HEAD")
        self.artifacts = self.project / "_bmad-output"
        self.artifacts.mkdir()
        self.work = self.project / ".aisef" / "worktrees" / SID
        _git(self.project, "worktree", "add", "-q", str(self.work), "-b", f"story/{SID}")
        self.story = Story(id=SID, epic_id="EPIC-04", title="CLI repair", covers=["FR-4"],
                           acceptance_criteria=["repair exits 0 after appending the missing newline"],
                           write_scope=list(SCOPE))

    def tearDown(self):
        subprocess.run(["git", "worktree", "remove", "--force", str(self.work)], cwd=self.project, check=False)
        self._tmp.cleanup()

    def implement(self, client, *, workdir=None, retries=1):
        return implement_story(
            self.story, project=self.project, workdir=workdir or self.work, artifact_root=self.artifacts,
            client=client,
            config=Config({**DEFAULTS, "tools.test": "true", "tools.lint": "true", "run.max_retries": retries}),
        )

    def events(self, name):
        return list(EvidenceStore(self.artifacts).read(SID).of(NOTE, name))


class TestRetryStartsClean(HygieneCase):

    def test_A_tracked_out_of_scope_files_are_restored_before_the_retry_and_the_story_completes(self):
        c = Developer()
        out = self.implement(c)
        self.assertEqual(c.develop_calls, 2, out.summary())
        first = out.attempts[0]
        self.assertIn("write scope", [x.name for x in first.gate.failures])
        seen = c.seen[0]
        self.assertEqual(seen["ledger"], LEDGER, "ledger.py must be back to the frozen candidate")
        self.assertEqual(seen["store"], STORE, "store.py must be back to the frozen candidate")
        self.assertEqual(seen["status"], "", "the retry opens on a clean tree")
        self.assertTrue(out.done, out.summary())

    def test_B_a_violating_untracked_file_is_removed_and_only_that(self):
        def first(work):
            ledgerlock_pattern(work)
            (work / "ledgerlock" / "scratch_notes.py").write_text("tmp\n", encoding="utf-8")
        c = Developer(first=first)
        out = self.implement(c)
        seen = c.seen[0]
        self.assertFalse(seen["scratch"], "the untracked out-of-scope file the session created is gone")
        self.assertEqual(seen["format"], FORMAT, "an untouched tracked file stays untouched")
        (rec,) = self.events(RECOVERY)
        self.assertEqual(rec.detail["untracked"], ["ledgerlock/scratch_notes.py"])
        self.assertTrue(out.done, out.summary())

    def test_C_the_diff_scope_guard_no_longer_blocks_a_harmless_command_on_the_retry(self):
        c = Developer()
        self.implement(c)
        seen = c.seen[0]
        self.assertTrue(seen["guard_allowed"], seen["guard_reason"])

    def test_D_every_violating_path_is_restored_deterministically(self):
        def first(work):
            ledgerlock_pattern(work)
            (work / "ledgerlock" / "format.py").unlink()                                   # deleted tracked file
            (work / "ledgerlock" / "scratch_notes.py").write_text("tmp\n", encoding="utf-8")
        c = Developer(first=first)
        out = self.implement(c)
        seen = c.seen[0]
        self.assertEqual((seen["ledger"], seen["store"], seen["format"]), (LEDGER, STORE, FORMAT))
        self.assertFalse(seen["scratch"])
        self.assertEqual(seen["status"], "")
        (rec,) = self.events(RECOVERY)
        self.assertEqual(rec.detail["tracked"],
                         ["ledgerlock/format.py", "ledgerlock/ledger.py", "ledgerlock/store.py"])
        self.assertEqual(rec.detail["untracked"], ["ledgerlock/scratch_notes.py"])
        self.assertTrue(out.done, out.summary())

    def test_E_legitimate_in_scope_candidate_changes_are_kept(self):
        c = Developer()
        out = self.implement(c)
        seen, first = c.seen[0], out.attempts[0]
        self.assertIn("def repair(argv):\n    return 0", seen["cli"], "attempt 1's in-scope change survives")
        self.assertEqual(seen["head"], first.candidate, "HEAD is still the frozen candidate")
        self.assertEqual(_git(self.work, "show", f"{first.candidate}:ledgerlock/ledger.py"), LEDGER.rstrip("\n"),
                         "the candidate never carried the out-of-scope change")

    def test_E2_when_the_freeze_refused_pre_staged_out_of_scope_paths_the_in_scope_work_is_still_kept(self):
        def first(work):
            ledgerlock_pattern(work)
            _git(work, "add", "ledgerlock/ledger.py")          # staged outside scope: commit_paths refuses the freeze
        c = Developer(first=first)
        out = self.implement(c)
        seen = c.seen[0]
        self.assertEqual(seen["ledger"], LEDGER)
        self.assertEqual(seen["store"], STORE)
        self.assertEqual(seen["staged"], "", "nothing outside scope stays staged")
        self.assertIn("def repair(argv):\n    return 0", seen["cli"], "uncommitted in-scope work is kept")
        self.assertTrue(out.done, out.summary())

    def test_F_unrelated_untracked_files_are_preserved(self):
        (self.work / ".venv").mkdir()
        (self.work / ".venv" / "x.txt").write_text("ignored\n", encoding="utf-8")          # gitignored
        (self.work / ".opencode" / "plugin").mkdir(parents=True)
        (self.work / ".opencode" / "plugin" / "g.ts").write_text("// guard\n", encoding="utf-8")   # harness-owned

        def first(work):
            ledgerlock_pattern(work)
            (work / ".coverage").write_bytes(b"\x00")                                        # tool artifact

        c = Developer(first=first)
        out = self.implement(c)
        for rel in (".venv/x.txt", ".opencode/plugin/g.ts", ".coverage"):
            self.assertTrue((self.work / rel).exists(), rel)
        self.assertEqual(c.seen[0]["ledger"], LEDGER)
        self.assertTrue(out.done, out.summary())
        for rec in self.events(RECOVERY):
            self.assertEqual(rec.detail["untracked"], [])

    def test_G_reviewer_tree_restoration_is_unchanged_and_is_not_retry_recovery(self):
        def reviewer_writes(work):
            (work / "ledgerlock" / "reviewer_note.py").write_text("x\n", encoding="utf-8")
        c = Developer(first=in_scope_fix, reviewer_writes=reviewer_writes)
        self.implement(c, retries=0)
        self.assertFalse((self.work / "ledgerlock" / "reviewer_note.py").exists(), "reviewer writes are reverted")
        ev = EvidenceStore(self.artifacts).read(SID)
        self.assertTrue(any(e.name == "review:immutable" and not e.ok for e in ev.events))
        self.assertEqual(self.events(RECOVERY), [], "reviewer clean-up is the existing layer, not retry recovery")
        self.assertEqual(self.events(VIOLATION), [])

    def test_H_a_genuine_write_scope_violation_still_fails_the_attempt(self):
        c = Developer()
        out = self.implement(c)
        first = out.attempts[0]
        self.assertFalse(first.ok)
        scope = next(x for x in first.gate.checks if x.name == "write scope")
        self.assertFalse(scope.passed)
        self.assertIn("ledgerlock/ledger.py", scope.detail)
        self.assertIn("ledgerlock/store.py", scope.detail)

    def test_I_evidence_records_the_violation_and_the_recovery_with_exact_paths(self):
        c = Developer()
        out = self.implement(c)
        first = out.attempts[0]
        (viol,) = self.events(VIOLATION)
        self.assertFalse(viol.ok)
        self.assertEqual(viol.detail["attempt"], 1)
        self.assertEqual(viol.detail["tracked"], ["ledgerlock/ledger.py", "ledgerlock/store.py"])
        self.assertEqual(viol.detail["untracked"], [])
        (rec,) = self.events(RECOVERY)
        d = rec.detail
        self.assertTrue(rec.ok, d)
        self.assertEqual(d["attempt"], 1)
        self.assertEqual(d["next_attempt"], 2)
        self.assertEqual(d["candidate"], first.candidate)
        self.assertEqual(d["tracked"], ["ledgerlock/ledger.py", "ledgerlock/store.py"])
        self.assertEqual(d["untracked"], [])
        self.assertTrue(any("git restore" in a for a in d["actions"]), d["actions"])
        self.assertEqual(d["status_after"], [])
        self.assertLess(viol.seq, rec.seq)
        log = (self.artifacts / "run.log").read_text(encoding="utf-8")
        self.assertIn("retry recovery", log)

    def test_J_dirt_no_attempt_of_this_story_made_is_never_deleted_and_no_session_is_launched(self):
        mine = self.work / "ledgerlock" / "operator_notes.py"
        mine.write_text("mine\n", encoding="utf-8")                 # untracked, not ignored, outside scope
        c = Developer()
        out = self.implement(c)
        self.assertEqual(c.develop_calls, 0, "a developer on this tree could only be blocked by the guard")
        self.assertEqual(mine.read_text(encoding="utf-8"), "mine\n", "never remove what the harness did not make")
        self.assertIn("ledgerlock/operator_notes.py", out.blocked_reason)
        (rec,) = self.events(RECOVERY)
        self.assertFalse(rec.ok)
        self.assertEqual(rec.detail["unattributed"], ["ledgerlock/operator_notes.py"])

    def test_K_the_write_scope_message_says_the_harness_restores_and_names_an_allowed_way_out(self):
        v = check_diff_scope(["ledgerlock/ledger.py", "ledgerlock/cli.py"], ["ledgerlock/cli.py"])
        self.assertFalse(v.allowed)
        self.assertTrue(v.reason.startswith("1 files changed outside write_scope: ledgerlock/ledger.py"), v.reason)
        self.assertIn("before the next attempt", v.reason)
        self.assertIn("git restore -- ledgerlock/ledger.py", v.reason)
        self.assertNotIn("Revert them", v.reason)

    def test_L_without_isolation_the_harness_never_touches_the_user_tree(self):
        c = Developer()
        self.implement(c, workdir=self.project)
        self.assertEqual(self.events(RECOVERY), [])
        self.assertEqual(c.develop_calls, 2)
        self.assertTrue((self.project / "ledgerlock" / "ledger.py").exists())


if __name__ == "__main__":
    unittest.main()
