"""V2.1 mutation survivors, audit batch A07: aisef2/app/confine.py (_worktree, wrap).

The audit of this batch found two refusals whose identifying elements the existing tests
(tests/v2/test_v21_confine.py) never asserted, and one the operator document quotes:

* a measurement that cannot make its workspace as a worktree is refused with a problem that says WHICH stage failed
  (the workspace, as a worktree of the repository) and names the repository's path as a token of its own, apart from
  git's reason: the operator reads it from `RUN.json.confinement.problems` / `aisef run --check`;
* a client whose directory holds HOME or the workspace is refused naming that directory AS the client's — the one the
  operator document (docs/v2.1/SANDBOX-LINUX.md, section 2) quotes: "the client's directory ... holds HOME" — which is
  the resolved directory of the client, not necessarily a path the operator wrote.

Nothing here runs bubblewrap, a probe or a client; every file is in a directory of the test's own."""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import confine  # noqa: E402
from aisef2.orchestrate import workspace  # noqa: E402
from tests.v2 import isolated_git  # noqa: E402

#: what a run may ask for (the shared network: a session must reach its provider)
SPEC = {"backend": "bwrap", "bwrap": "/usr/bin/bwrap", "network": "host", "read_only": []}
ENVIRON = {"PATH": "/usr/bin:/bin"}
#: what makes a path run on into the text after it: a word character or a dash, or a separator or a dot that goes on
#: into one (`/repo` + `fatal`, `/repo` + `.git`); a delimiter — `: `, ` - `, `. `, a space, the end — does not
RUNS_ON = re.compile(r"[\w-]|[/\\.](?=[\w-])")
#: the stage a worktree problem names: the measurement's WORKSPACE, made a WORKTREE of the repository (the other stage,
#: the repository's own creation, says "repository")
STAGE = re.compile(r"worktree|workspace")


def stage_words(said: str, repo: pathlib.Path) -> str:
    """What the message says besides the repository's path."""
    return said.replace(str(repo), "")


def is_a_token(said: str, path: pathlib.Path) -> bool:
    """The first mention of `path` in `said` is followed by something that does not run on from it (a delimiter, or the
    end of the message): the path can be copied out of the message as it is."""
    after = said[said.index(str(path)) + len(str(path)):]
    return RUNS_ON.match(after) is None


class WorktreeStageRefusal(unittest.TestCase):
    """A measurement whose workspace cannot be made a worktree of the repository (git refused it) is a problem of the
    report — the run's refusal text and `--check`'s confinement.problems — which says that it is the WORKSPACE as a
    worktree that failed (not the measurement repository: that stage has its own problem), names the repository's path
    as a token the operator can copy, and carries git's own reason. Nothing runs under confinement.

    Pins aisef2/app/confine.py::_worktree [41, 42]."""

    def measured(self, fails):
        """(where, report) of confine.measure with git stubbed: `fails(args)` says whether that git call fails."""
        def git(repo, *args):
            bad = fails(args)
            return subprocess.CompletedProcess(["git", *args], 128 if bad else 0, "",
                                               "fatal: boom, out of space" if bad else "")
        with tempfile.TemporaryDirectory() as t:
            where = pathlib.Path(os.path.realpath(t)) / "run" / "confinement"
            with mock.patch.object(workspace, "git", git):
                rep = confine.measure(SPEC, where, None, system="linux", environ=ENVIRON)
        return where, rep

    def test_the_stage_that_failed_is_the_workspace_as_a_worktree(self):
        where, rep = self.measured(lambda args: "worktree" in args)
        [said] = rep["problems"]
        self.assertIn(str(where / "repo"), said)                    # where
        self.assertIn("boom, out of space", said)                    # git's reason
        reason = stage_words(said, where / "repo")
        self.assertRegex(reason, STAGE)                              # which stage: the workspace, made a worktree of it

    def test_the_repository_path_is_a_token_of_its_own(self):
        """git's text opens with a word (`fatal:`, `error:`, `refused:`): the path must not run into it, or the
        operator copying the path out of the message gets another path."""
        where, rep = self.measured(lambda args: "worktree" in args)
        [said] = rep["problems"]
        self.assertTrue(is_a_token(said, where / "repo"), said)

    def test_a_repository_git_refuses_to_run_in_is_told_the_same_way(self):
        """The likeliest real cause: the run's repository holds a configuration key that is not inert, so the runner's
        own git refuses (exit 128, `refused: ...`) before running anything there. The same stage, the same path
        token."""
        with tempfile.TemporaryDirectory() as t:
            tmp = pathlib.Path(os.path.realpath(t))
            repo = tmp / "repo"
            repo.mkdir()
            isolated_git.git(repo, "init", "-q", "-b", "main")
            isolated_git.git(repo, "commit", "-q", "--allow-empty", "-m", "base")
            isolated_git.git(repo, "config", "core.editor", "false")      # not an inert key: the runner's git refuses
            rep = confine.measure(SPEC, tmp / "run" / "confinement", None, repo, system="linux", environ=ENVIRON)
        [said] = rep["problems"]
        self.assertRegex(stage_words(said, repo), STAGE)
        self.assertTrue(is_a_token(said, repo), said)


class ClientDirectoryRefusal(unittest.TestCase):
    """A client installed where its directory, bound read-only, would expose HOME (or the runs) is refused, and the
    refusal names that directory as the CLIENT's: the directory printed is the resolved directory of the client's real
    path — through a symlink it is not a path the operator wrote — so what the path is, is said at the path. The
    operator document quotes the refusal as "the client's directory ... holds HOME".

    Pins aisef2/app/confine.py::wrap [54]."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(os.path.realpath(t.name))
        self.home, self.ws = self.tmp / "home", self.tmp / "run" / "ws"
        self.home.mkdir()
        self.ws.mkdir(parents=True)
        bwrap = self.tmp / "bwrap"
        bwrap.write_text("#!/bin/sh\nexit 97\n", encoding="utf-8")      # only its existence and mode are looked at
        bwrap.chmod(0o755)
        self.spec = dict(SPEC, bwrap=str(bwrap))
        self.env = {"PATH": "/usr/bin:/bin", "HOME": str(self.home), "LANG": "C"}
        self.exe = self.home / "opencode"                  # the client in HOME: its directory is HOME itself
        self.exe.write_text("#!/bin/sh\n", encoding="utf-8")

    def refusal(self, exe: pathlib.Path) -> str:
        with self.assertRaises(confine.Unavailable) as raised:
            confine.wrap(self.spec, [str(exe), "run"], self.env, str(self.ws), str(exe), system="linux")
        return str(raised.exception)

    def assert_names_the_clients_directory(self, said: str, directory: pathlib.Path) -> None:
        self.assertIn(str(directory), said)
        self.assertTrue(is_a_token(said, directory), said)  # the directory itself, not a file or a path below it
        before = said.split(str(directory), 1)[0]
        self.assertIn("client", before.lower(), said)       # what the path is: said where the path is

    def test_the_directory_refused_is_named_as_the_clients(self):
        said = self.refusal(self.exe)
        self.assert_names_the_clients_directory(said, self.home)
        self.assertRegex(said, "holds HOME")

    @unittest.skipUnless(os.name == "posix", "a symlink to the client needs no privilege here")
    def test_a_client_reached_through_a_link_is_refused_naming_its_resolved_directory(self):
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        link = bin_dir / "opencode"
        link.symlink_to(self.exe)
        said = self.refusal(link)
        self.assert_names_the_clients_directory(said, self.home)      # resolved: HOME, not the link's directory


if __name__ == "__main__":
    unittest.main()
