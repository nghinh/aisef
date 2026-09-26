"""Phase 8A group C — discovery debt for the NEEDS_TEST ownership / scheduler sites SS-37, SS-38, SS-40,
SS-41, SS-42, SS-43, SS-53 (closure-evidence/hardening/sibling-scan.json). Every test asserts the INVARIANT
(docs/INVARIANTS.md) through the harness's own code path and checks that the suspicious path was actually
exercised; a red assertion is marked ``expectedFailure`` under its SS id (CONFIRMED), a green one stays as a
negative control. No OpenCode, no network, no Docker (tests/__init__.py swaps the host provider in).
"""
from __future__ import annotations

import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import tests  # noqa: E402,F401

from aisef.cli._common import EXIT_OK  # noqa: E402
from aisef.cli.implement import cmd_verify  # noqa: E402
from aisef.clients.base import Capability, ClientAdapter, Support  # noqa: E402
from aisef.clients.stream import RunResult  # noqa: E402
from aisef.config import DEFAULTS, Config  # noqa: E402
from aisef.control import scheduler  # noqa: E402
from aisef.control.normalize import Story, effective_write_scope  # noqa: E402
from aisef.control.state import SprintState, StateStore, StoryRecord  # noqa: E402
from aisef.harness.guardrails import changed_files, run_guard  # noqa: E402
from aisef.harness.observe import EvidenceStore  # noqa: E402
from aisef.phases.deploy import generate, pre_deploy, write_ci_workflow  # noqa: E402
from aisef.phases.run import Plan, _effective_waves  # noqa: E402
from tests.test_deploy import DeployTestCase  # noqa: E402
from tests.test_implement import ImplementTestCase, ScriptedClient  # noqa: E402

SID = "STORY-01-01"


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout.strip()


def _repo(tmp) -> Path:
    repo = Path(tmp); repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main"); _git(repo, "config", "user.email", "t@t"); _git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("a\n", encoding="utf-8"); _git(repo, "add", "-A"); _git(repo, "commit", "-qm", "c")
    return repo


# ---------------------------------------------------------------- FAM-OWNERSHIP / INV-I.3

class _GuardAtOpen(ScriptedClient):
    """Computes the `diff-scope` verdict the hook would return for the session's very first Bash call —
    same function, same env — before the developer writes anything."""

    def __init__(self):
        super().__init__(); self.verdicts = []

    def run(self, spec):
        self.verdicts.append(run_guard("diff-scope", {"tool_name": "Bash", "tool_input": {"command": "ls"}},
                                       env=dict(spec.env), project_root=str(spec.workdir)))
        return super().run(spec)


class TestSS37StorySessionDeclaresPreexistingDirt(ImplementTestCase):
    """SS-37 — `run_attempt` builds the story session env without ENV_BASELINE_DIRTY (planning/mockup set it),
    and `recover_out_of_scope` only runs when workdir != project; under --no-isolate an operator's dirty
    tracked file outside scope is blamed on the developer by every `diff-scope` call. Invariant I.3."""

    # GREEN since F4 (SS-37: one ownership rule for every consumer), 2026-09-16
    def test_operator_dirt_outside_scope_does_not_block_the_developers_first_tool_call(self):
        _git(self.project, "config", "user.email", "t@t"); _git(self.project, "config", "user.name", "t")
        (self.project / "notes.txt").write_text("v1\n", encoding="utf-8"); _git(self.project, "add", "-A"); _git(self.project, "commit", "-qm", "c")
        (self.project / "notes.txt").write_text("v2 — operator's uncommitted edit\n", encoding="utf-8")
        c = _GuardAtOpen()
        out = self.implement(c)                       # workdir == project: --no-isolate
        self.assertTrue(c.verdicts or out.blocked_reason, "neither a session nor a typed refusal")
        if c.verdicts:
            self.assertTrue(c.verdicts[0].allowed, c.verdicts[0].reason)


# ---------------------------------------------------------------- FAM-OWNERSHIP / INV-I.1

class TestSS38ClientLocalSettingsAreClientOwned(unittest.TestCase):
    """SS-38 — HARNESS_OWNED names `.claude/settings.json` only; Claude Code persists per-machine permission
    grants in `.claude/settings.local.json` (this repository carries one, hidden only by the user's global
    gitignore), which `changed_files` then attributes to the story. Invariant I.1."""

    # GREEN since F4 (SS-38: one ownership rule for every consumer), 2026-09-16
    def test_settings_local_json_is_not_a_story_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _repo(Path(tmp) / "repo")
            # A developer's *global* gitignore may hide this file (it does on the machine this was written on);
            # the harness cannot rely on that, so the test measures a project with no such shield.
            (Path(tmp) / "no-excludes").write_text("", encoding="utf-8")
            _git(repo, "config", "core.excludesFile", str(Path(tmp) / "no-excludes"))
            (repo / ".claude").mkdir(); (repo / ".claude" / "settings.local.json").write_text("{}", encoding="utf-8")
            self.assertIn("settings.local.json", _git(repo, "status", "--porcelain", "-uall"))   # git does see it
            self.assertEqual(changed_files(str(repo)), [])


class TestSS41PreexistingInScopeFileIsNotSweptIntoTheCandidate(ImplementTestCase):
    """SS-41 — `commit_paths` stages `git add -A -- <scope dirs>`: an untracked operator fixture that lay under a
    granted directory before the session opened becomes part of the frozen candidate, attributed to the
    developer, although `run_attempt` snapshotted it as pre-existing. Invariant I.1."""

    # GREEN since F4 (SS-41: one ownership rule for every consumer), 2026-09-16
    def test_an_untracked_operator_fixture_under_scope_is_not_committed_as_the_developers_work(self):
        _git(self.project, "config", "user.email", "t@t"); _git(self.project, "config", "user.name", "t")
        (self.project / "goc.txt").write_text("g\n", encoding="utf-8"); _git(self.project, "add", "-A"); _git(self.project, "commit", "-qm", "goc")
        wt = self.project / ".aisef" / "worktrees" / SID
        _git(self.project, "worktree", "add", "-q", str(wt), "-b", f"story/{SID}")
        fixture = "src/fixtures/operator.json"
        (wt / "src" / "fixtures").mkdir(parents=True); (wt / fixture).write_text("{}", encoding="utf-8")   # before the session
        self.implement(ScriptedClient(), workdir=wt)   # the developer writes src/a.py only
        committed = _git(wt, "show", "--name-only", "--format=", "HEAD").splitlines()
        self.assertIn("src/a.py", committed, committed)   # the freeze really committed by scope
        attributed = any(fixture in (e.detail.get("preexisting") or [])
                         for e in EvidenceStore(self.artifacts).read(SID).events)
        self.assertTrue(fixture not in committed or attributed,
                        f"{fixture} pre-dated the session yet is in candidate {committed} with no attribution")


# ---------------------------------------------------------------- FAM-OWNERSHIP / INV-J.1

class TestSS40VerifyWithoutScopeIsNotAPass(unittest.TestCase):
    """SS-40 — the generated CI step is a bare `aisef verify`; `cmd_verify` with no --write-scope skips the scope
    check and exits 0, so the "post-hoc guard" step is green on every checkout. Invariant J.1 (the guard reads
    the effective scope — an unconfigured guard is not a passing one)."""

    # GREEN since F4 (SS-40: one ownership rule for every consumer), 2026-09-16
    def test_bare_verify_as_generated_for_ci_does_not_exit_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _repo(tmp)
            ci = write_ci_workflow(repo).read_text(encoding="utf-8")
            step = next(line for line in ci.splitlines() if line.strip().startswith("run:") and " verify" in line)
            # F4 (SS-40): the generated step now carries the scope source (a repository variable; empty fails closed) —
            # and a BARE verify, however invoked, is UNCONFIGURED, never a pass
            self.assertIn("--write-scope", step, step)
            with redirect_stdout(io.StringIO()) as out:
                rc = cmd_verify(SimpleNamespace(project=str(repo), write_scope="", story=""))
            self.assertNotEqual(rc, EXIT_OK, out.getvalue())


class _CaptureSpec(ClientAdapter):
    id = "capture"

    def available(self): return True
    def capabilities(self): return {c: Support.NATIVE for c in Capability}

    def run(self, spec):
        self.spec = spec; return RunResult(ok=True, text="", cost_usd=0.1)


class TestSS42DevsecopsSessionCarriesAWriteScope(DeployTestCase):
    """SS-42 — `generate()` opens the devsecops session with a RunSpec whose env is empty; a project with compiled
    hooks (`.claude/settings.json`, loaded as project settings) then evaluates `effective_scope({})` ==
    PLANNING_SCOPE and blocks the Dockerfile the phase itself demands. Invariant J.1."""

    # GREEN since F4 (SS-42: one ownership rule for every consumer), 2026-09-16
    def test_the_guard_env_handed_to_the_devsecops_client_allows_writing_the_dockerfile(self):
        client = _CaptureSpec()
        generate(self.project, client, config=self.config())
        env = dict(client.spec.env)   # exactly what the hook child process would read
        v = run_guard("write-scope", {"tool_name": "Write", "tool_input": {"file_path": str(self.project / "Dockerfile")}},
                      env=env, project_root=str(self.project))
        self.assertTrue(v.allowed, v.reason)


# ---------------------------------------------------------------- FAM-OWNERSHIP / INV-P.1, INV-A.3

class TestSS43PreDeployGradesOneTree(DeployTestCase):
    """SS-43 — pre-deploy runs the suite in a clean worktree of HEAD (and signs that SHA) but checks
    Dockerfile / CI / runbook on the working tree: the report can say "Dockerfile: PASS" for a candidate that
    has no Dockerfile. Invariant P.1 / A.3."""

    # GREEN since F4 (SS-43: one ownership rule for every consumer), 2026-09-16
    def test_an_uncommitted_dockerfile_is_not_a_pass_bound_to_head(self):
        _git(self.project, "init", "-q"); _git(self.project, "config", "user.email", "t@t"); _git(self.project, "config", "user.name", "t")
        _git(self.project, "add", "-A"); _git(self.project, "commit", "-qm", "head without Dockerfile")
        (self.project / "Dockerfile").write_text("FROM alpine\n", encoding="utf-8")   # working tree only
        self.approve_everything(); self.finish_a_story()
        report = pre_deploy(self.project, config=self.config(**{"verify.unit": "true", "sandbox.use_docker": False}))
        qa = report.as_dict()["qa"]
        self.assertEqual(qa["tree"], "clean-worktree", qa)   # the suite really graded HEAD
        self.assertNotIn("Dockerfile", _git(self.project, "ls-tree", "--name-only", "HEAD"))
        chk = next(c for c in report.checks if c.name == "Dockerfile")
        self.assertTrue(not chk.passed or "work" in chk.detail.lower(),
                        f"Dockerfile check {chk.outcome.value!r} detail={chk.detail!r} bound to {qa['clean_tree'][:8]}, "
                        f"which has no Dockerfile")


# ---------------------------------------------------------------- FAM-SCHEDULER / INV-O.1, INV-J.1

class TestSS53SchedulerReadsTheEffectiveScope(unittest.TestCase):
    """SS-53 — `_effective_waves` partitions on declared scope + bootstrap grants; the manifests and test
    directories `effective_write_scope` grants to every story never reach `scopes_conflict`, so two stories
    both allowed to edit `pyproject.toml` run in one wave. Invariant O.1 / J.1 (one effective scope)."""

    # GREEN since F4 (SS-53: one ownership rule for every consumer), 2026-09-16
    def test_stories_sharing_a_granted_path_do_not_share_a_wave(self):
        def story(sid, path):
            return Story(id=sid, epic_id="EPIC-01", title=sid, write_scope=[path], verification_contract=["unit"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); art = root / "_bmad-output"; art.mkdir()
            for f in ("pyproject.toml", "conftest.py", "pytest.ini"):   # past bootstrap: no bootstrap grant
                (root / f).write_text("", encoding="utf-8")
            cfg = Config({**DEFAULTS, "tools.test": "python -m pytest -v"})
            stories = {s.id: s for s in (story("STORY-01-01", "src/keys.py"), story("STORY-01-02", "src/hash.py"))}
            st = StateStore(art); st.save(SprintState(stories={sid: StoryRecord(id=sid, epic_id="EPIC-01") for sid in stories}))
            plan = Plan(stories=stories, waves={"EPIC-01": [list(stories)]})
            eff = {sid: effective_write_scope(s, root) for sid, s in stories.items()}
            for sid in stories:   # the guard really grants the shared paths to both
                self.assertIn("pyproject.toml", eff[sid], eff[sid]); self.assertIn("tests", eff[sid], eff[sid])
            for _, group in _effective_waves(plan, "EPIC-01", project=root, config=cfg, state=st):
                for a in group:
                    for b in group:
                        if a < b:
                            shared = sorted(set(eff[a]) & set(eff[b]))
                            self.assertFalse(scheduler.scopes_conflict(scheduler.Story(id=a, write_scope=tuple(eff[a])),
                                                                       scheduler.Story(id=b, write_scope=tuple(eff[b]))),
                                             f"wave {group}: {a} and {b} both may write {shared}")


if __name__ == "__main__":
    unittest.main()
