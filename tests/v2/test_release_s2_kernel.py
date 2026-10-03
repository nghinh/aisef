"""V2.0 release charter §7 (S2 fix window) — the kernel corrections and their deterministic reproducers:

* B7  a story whose candidate is the branch tip (no change) and whose post-merge proof fails no longer resets the
      branch to the commit before the previous story's merge: the previous story stays.
* B4  no git the kernel runs executes a configuration the repository (or the operator's global file) names: an
      fsmonitor, a clean filter, an include, a worktree-scope key, a hook; a checkout whose gitfile points elsewhere is
      never moved.
* B6  a checkout move leaves no ignored file and no nested repository behind.
* KA-09  the read-only scope of a review never follows a link: a link's target keeps its mode, a dangling link raises
      nothing.

Each reproducer has a control that shows the vector is live without the correction (POSIX, where the control runs a
shell command through git)."""

from __future__ import annotations

import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import ObligationRole as R, Owner  # noqa: E402
from aisef2.orchestrate import adapters  # noqa: E402
from aisef2.orchestrate import workspace as w  # noqa: E402
from aisef2.orchestrate.adapters import ResourceUnavailable  # noqa: E402
from tests.v2 import test_c2_k_presat_001 as presat  # noqa: E402
from tests.v2 import test_p6_orchestration as e2e  # noqa: E402

POSIX = os.name == "posix"


def raw_git(repo, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """git as an unguarded caller would run it: the repository's and the operator's configuration in force."""
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                          env={**os.environ, **(env or {})})


def marker_command(marker: pathlib.Path) -> str:
    """A command that appends one line to `marker` each time anything runs it."""
    return f"echo ran >> '{marker}'"


class Repo(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory(prefix="aisef2-s2-")
        self.addCleanup(d.cleanup)
        self.tmp = pathlib.Path(d.name).resolve()
        self.repo, self.base = e2e.make_repo(self.tmp)
        self.marker = self.tmp / "executed"
        (self.tmp / "ws").mkdir()
        self.ws = w.GitWorkspace(self.repo, self.tmp / "ws")

    def configure(self, *kv: str, where=None) -> None:
        self.assertEqual(raw_git(where or self.repo, "config", *kv).returncode, 0)

    def ran(self) -> int:
        return len(self.marker.read_text(encoding="utf-8").splitlines()) if self.marker.exists() else 0

    def control(self, *args: str, env: dict | None = None) -> int:
        """Runs `args` as an unguarded caller would (POSIX only) and returns how often the configured command ran."""
        if POSIX:
            before = self.ran()
            raw_git(self.repo, *args, env=env)
            self.assertGreater(self.ran(), before, "the control did not run the configured command")
        return self.ran()

    def assertRefused(self, where, key: str, ran: int) -> None:
        self.assertIn(key, w.config_problems(where))
        p = w.git(where, "status", "--porcelain")
        self.assertEqual(p.returncode, w.REFUSED)
        self.assertIn(key, p.stderr)
        self.assertEqual(self.ran(), ran, "a configured command ran under the kernel's git")


class GitConfiguration(Repo):
    def test_inert_keys_are_accepted(self):
        for kv in (("user.name", "n"), ("user.email", "e@x"), ("core.autocrlf", "false"), ("color.ui", "auto"),
                   ("branch.main.remote", "origin"), ("remote.origin.url", "/elsewhere")):
            self.configure(*kv)
        self.assertEqual(w.config_problems(self.repo), [])
        self.assertEqual(w.git(self.repo, "status", "--porcelain").returncode, 0)

    def test_an_fsmonitor_is_refused(self):
        self.configure("core.fsmonitor", marker_command(self.marker))
        self.assertRefused(self.repo, "core.fsmonitor", self.control("status"))

    def test_the_refusal_is_a_whole_result_that_names_every_key(self):
        """What a refused call returns, exactly: the command it would have run, REFUSED, nothing on stdout, and every
        key that is not inert, in order — a caller reads why, and nothing ran."""
        self.configure("core.fsmonitor", marker_command(self.marker))
        self.configure("diff.evil.textconv", marker_command(self.marker))
        p = w.git(self.repo, "log", "-1")
        self.assertEqual((p.args, p.returncode, p.stdout, p.stderr),
                         (["git", "-C", str(self.repo), "log", "-1"], w.REFUSED, "",
                          f"refused: the repository configuration at {self.repo} names core.fsmonitor, diff.evil.textconv "
                          "(not inert)"))
        self.assertEqual(self.ran(), 0)

    def test_a_clean_filter_is_refused(self):
        pathlib.Path(self.repo, ".gitattributes").write_text("*.py filter=evil\n", encoding="utf-8")
        self.configure("filter.evil.clean", marker_command(self.marker))
        pathlib.Path(self.repo, "app/calc.py").write_text(e2e.CALC + "# changed\n", encoding="utf-8")
        ran = self.control("add", "-A")
        self.assertRefused(self.repo, "filter.evil.clean", ran)
        with self.assertRaises(RuntimeError):     # the developer's last step is refused, nothing staged through the filter
            w.commit_all(self.repo, "through a filter")
        self.assertEqual(self.ran(), ran)

    def test_an_include_is_refused_and_never_followed(self):
        included = self.tmp / "included.cfg"
        included.write_text(f"[core]\n\tfsmonitor = {marker_command(self.marker)}\n", encoding="utf-8")
        self.configure("include.path", str(included))
        self.assertRefused(self.repo, "include.path", self.control("status"))
        self.assertNotIn("core.fsmonitor", w.config_problems(self.repo))     # listed, not followed

    def test_a_worktree_scope_key_is_refused(self):
        wt = self.ws.checkout("wt-S1", self.base)
        self.configure("extensions.worktreeConfig", "true")
        self.configure("--worktree", "core.fsmonitor", marker_command(self.marker), where=wt.path)
        self.assertRefused(wt.path, "core.fsmonitor", 0)
        with self.assertRaises(ResourceUnavailable):
            self.ws.move(wt, self.base)
        self.assertEqual(self.ran(), 0)

    def test_the_operator_s_global_and_system_files_are_not_read(self):
        home = self.tmp / "home"
        home.mkdir()
        evil = home / ".gitconfig"
        evil.write_text(f"[core]\n\tfsmonitor = {marker_command(self.marker)}\n", encoding="utf-8")
        planted = {"HOME": str(home), "GIT_CONFIG_GLOBAL": str(evil), "GIT_CONFIG_SYSTEM": str(evil), "XDG_CONFIG_HOME": str(home)}
        ran = self.control("status", env=planted)
        saved = {k: os.environ.get(k) for k in planted}
        os.environ.update(planted)
        try:
            self.assertEqual(w.config_problems(self.repo), [])
            self.assertEqual(w.git(self.repo, "status", "--porcelain").returncode, 0)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.assertEqual(self.ran(), ran)

    def test_no_variable_of_the_caller_redirects_git_or_names_a_program_for_it(self):
        (self.tmp / "other-root").mkdir()
        other, other_base = e2e.make_repo(self.tmp / "other-root", {"other.txt": "another repository\n"})
        planted = {"GIT_DIR": str(pathlib.Path(other, ".git")), "GIT_WORK_TREE": other, "GIT_EXTERNAL_DIFF": marker_command(self.marker),
                   "GIT_CONFIG_PARAMETERS": "'core.fsmonitor'='" + marker_command(self.marker) + "'"}
        saved = {k: os.environ.get(k) for k in planted}
        os.environ.update(planted)
        try:
            self.assertEqual(w.git(self.repo, "rev-parse", "HEAD").stdout.strip(), self.base)   # this repository, not the other
            pathlib.Path(self.repo, "app/calc.py").write_text(e2e.CALC + "# changed\n", encoding="utf-8")
            self.assertEqual(w.git(self.repo, "diff").returncode, 0)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.assertEqual(self.ran(), 0)
        self.assertNotEqual(other_base, self.base)

    @unittest.skipUnless(POSIX, "a POSIX hook script")
    def test_a_hook_never_runs(self):
        hook = pathlib.Path(self.repo, ".git", "hooks", "post-checkout")
        hook.write_text(f"#!/bin/sh\n{marker_command(self.marker)}\n", encoding="utf-8")
        hook.chmod(0o755)
        wt = self.ws.checkout("wt-S1", self.base)          # worktree add runs post-checkout for an unguarded caller
        self.ws.move(wt, self.base)
        self.assertEqual(self.ran(), 0)
        raw_git(wt.path, "checkout", "--detach", self.base)                   # the control
        self.assertEqual(self.ran(), 1)

    def test_a_checkout_whose_gitfile_points_elsewhere_is_never_moved(self):
        (self.tmp / "other-root").mkdir()
        other, other_base = e2e.make_repo(self.tmp / "other-root")
        wt = self.ws.checkout("wt-S1", self.base)
        foreign = self.ws.__class__(other, self.tmp / "ws").checkout("wt-other", other_base)
        (wt.path / ".git").write_bytes((foreign.path / ".git").read_bytes())
        with self.assertRaises(ResourceUnavailable) as x:
            self.ws.move(wt, self.base)
        self.assertIn("gitfile", str(x.exception))


class CheckoutMove(Repo):
    def test_ignored_files_and_nested_repositories_do_not_survive_a_move(self):
        pathlib.Path(self.repo, ".gitignore").write_text("*.log\n", encoding="utf-8")
        base = w.commit_all(self.repo, "ignore logs")
        wt = self.ws.checkout("wt-S1", base)
        (wt.path / "planted.log").write_text("from an earlier step", encoding="utf-8")
        nested = wt.path / "vendor"
        nested.mkdir()
        self.assertEqual(raw_git(nested, "init", "-q").returncode, 0)
        (nested / "x.py").write_text("X = 1\n", encoding="utf-8")
        self.ws.move(wt, base)
        self.assertFalse((wt.path / "planted.log").exists())
        self.assertFalse(nested.exists())


class ReadOnlyScope(unittest.TestCase):
    def test_a_link_is_never_followed(self):
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t)
            checkout, outside = t / "checkout", t / "outside.txt"
            checkout.mkdir()
            outside.write_text("not the story's", encoding="utf-8")
            outside.chmod(0o644)
            (checkout / "a.py").write_text("A = 1\n", encoding="utf-8")
            try:
                os.symlink(outside, checkout / "link")
                os.symlink(t / "nowhere", checkout / "dangling")
            except (OSError, NotImplementedError) as e:      # Windows without the symlink privilege
                self.skipTest(f"no symlinks here: {e}")
            scope = adapters.confine("S1", str(checkout))
            self.assertEqual(stat.S_IMODE(outside.stat().st_mode), 0o644)
            self.assertFalse(os.access(checkout / "a.py", os.W_OK))
            adapters.unconfine(scope)
            self.assertTrue(os.access(checkout / "a.py", os.W_OK))
            self.assertEqual(stat.S_IMODE(outside.stat().st_mode), 0o644)


#: `sub` answers correctly until the flag exists — what a post-merge proof that disagrees with the candidate proofs
#: looks like (a non-deterministic subject, or the environment changing between the two)
def calc_with_flag(flag: pathlib.Path) -> str:
    return f"import os\n\n\ndef sub(a, b):\n    return a + b if os.path.exists({str(flag)!r}) else a - b\n" + e2e.ADD


class FlagAfterMerge:
    """The real merger; the flag is set right after each merge, before the post-merge proof."""

    def __init__(self, merger, flag: pathlib.Path) -> None:
        self.merger, self.flag, self.reverts = merger, flag, []

    def base(self) -> str:
        return self.merger.base()

    def merge(self, candidate: str):
        m = self.merger.merge(candidate)
        self.flag.write_text("set", encoding="utf-8")
        return m

    def revert(self, merged: str) -> None:
        self.reverts.append(merged)
        self.merger.revert(merged)


class NoChangeStoryAfterAMerge(presat.Fixture):
    def test_B7_a_failed_post_merge_proof_of_a_no_change_story_keeps_the_previous_story(self):
        flag = self.tmp / "flag"
        # one frozen plan: S1 introduces `add`; S2 then has nothing to introduce — it preserves `sub` and verifies `add`,
        # both satisfied at its parent, so its candidate is its parent, the branch tip
        plan = e2e.plan_of(self.merger.base(), e2e.obligation("C1", self.s1.id, "S1", R.INTRODUCE),
                           e2e.obligation("C0", self.s0.id, "S2", R.PRESERVE), e2e.obligation("C3", self.s1.id, "S2", R.VERIFY))
        # the prior story, through the developer: it commits as a real merge commit
        dev = e2e.Dev({"app/calc.py": calc_with_flag(flag), "tests/test_s1.py": e2e.TEST_ADD})
        s1 = self.story(plan, "S1", dev, tests_block=True)
        self.assertCommitted(s1)
        merged_s1 = self.merger.base()
        self.assertEqual(w.git(self.repo, "rev-list", "--parents", "-n", "1", merged_s1).stdout.split()[1:],
                         [self.base, dev.candidates[0]])
        merger = FlagAfterMerge(self.merger, flag)
        s2 = self.story(plan, "S2", e2e.Dev(outage=True), merger=merger, limits={o: 0 for o in Owner})
        self.assertFalse(s2.committed)
        post = [e for e in self.events("proof/verified", "S2") if e.data["candidate"] == merged_s1]
        self.assertIn("REFUTED", [e.data["verdict"] for e in post])          # the post-merge proof failed
        # the correction: nothing of S2 was merged, so nothing is reverted, and the previous story stays
        self.assertEqual(merger.reverts, [])
        self.assertEqual(self.merger.base(), merged_s1)
        self.assertIn("def add", w.git(self.repo, "show", "main:app/calc.py").stdout)


if __name__ == "__main__":
    unittest.main()
