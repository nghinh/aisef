"""The real workspace and merger: git worktrees the story owns as `StoryScope` resources, and a merger whose outcome is
typed from git's exit status and its unmerged-path list — never from stderr text (§26, V2-005). Every git the runner
starts runs without background maintenance, so nothing writes into a checkout after its release began.

Deletion authority (INV-MUTATION-AUTHORITY): nothing here removes a path by name. A checkout is removed by git, from
git's own registry of the worktree it added; a scratch directory is removed by the `TemporaryDirectory` handle that
created it. A directory that survives its release is a residual, reported, never forced."""

from __future__ import annotations

import os
import pathlib
import subprocess
import tempfile
from typing import Sequence

from aisef2.errors import InvariantError
from aisef2.journal.format2 import ResourceKind as K
from aisef2.orchestrate.adapters import Merge, MergeOutcome, ResourceUnavailable
from aisef2.probe.protocol import FULL_SHA
from aisef2.runtime.story_scope import Residual

_NO_BACKGROUND_GIT = {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "maintenance.auto", "GIT_CONFIG_VALUE_0": "false",
                      "GIT_CONFIG_KEY_1": "gc.auto", "GIT_CONFIG_VALUE_1": "0"}


def git(repo: str | os.PathLike, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, encoding="utf-8", errors="replace",
                          env={**os.environ, **_NO_BACKGROUND_GIT})


def _sha(repo: str | os.PathLike, rev: str) -> str:
    p = git(repo, "rev-parse", "--verify", f"{rev}^{{commit}}")
    sha = p.stdout.strip()
    if (p.returncode, FULL_SHA.fullmatch(sha) is not None) != (0, True):
        raise InvariantError(f"{rev!r} is not a commit of {repo}")
    return sha


class Scratch:
    """A story's scratch directory: a temporary directory whose handle the workspace created and holds; releasing it is
    the handle's own cleanup."""

    kind = K.SCRATCH

    def __init__(self, name: str, handle: tempfile.TemporaryDirectory) -> None:
        self.name, self._handle, self.path = name, handle, pathlib.Path(handle.name)

    def release(self) -> None:
        self._handle.cleanup()
        if self.path.exists():
            raise Residual(f"scratch {self.name} survived its cleanup at {self.path}")


class Checkout:
    """A worktree of the repository at one revision, owned by a story; released by git removing the worktree it
    registered (a residual if the directory survives that)."""

    kind = K.WORKTREE

    def __init__(self, name: str, repo: str, path: str | pathlib.Path, revision: str) -> None:
        self.name, self.repo, self.path, self.revision = name, repo, pathlib.Path(path), revision

    def release(self) -> None:
        removed = git(self.repo, "worktree", "remove", "--force", str(self.path))   # the registration goes with it
        if self.path.exists():
            raise Residual(f"worktree {self.name} survived its removal at {self.path} (git exited {removed.returncode})")


class GitWorkspace:
    """Worktrees under `root` for the repository at `repo`. `scratch` is a directory of the story's own; `checkout`
    is a detached worktree at a full SHA; `move` re-checks an owned worktree out at another SHA (the verifier moves
    its own checkout to the candidate; the implementer never touches it)."""

    def __init__(self, repo: str | os.PathLike, root: str | os.PathLike) -> None:
        self.repo, self.root = str(repo), pathlib.Path(root)

    def scratch(self, name: str) -> Scratch:
        try:
            handle = tempfile.TemporaryDirectory(prefix=f"{name}-", dir=self.root)
        except OSError as e:
            raise ResourceUnavailable(f"scratch {name}: {e}") from e
        return Scratch(name, handle)

    def checkout(self, name: str, revision: str) -> Checkout:
        if not FULL_SHA.fullmatch(revision):
            raise InvariantError(f"a checkout is named by a full SHA, not {revision!r}")
        path = self.root / name
        if path.exists():
            raise ResourceUnavailable(f"checkout {name}: {path} already exists")
        p = git(self.repo, "worktree", "add", "--detach", str(path), revision)
        if p.returncode != 0:
            raise ResourceUnavailable(f"checkout {name} at {revision[:12]}: git worktree add exited {p.returncode}")
        return Checkout(name, self.repo, path, revision)

    def move(self, checkout: Checkout, revision: str) -> None:
        if not FULL_SHA.fullmatch(revision):
            raise InvariantError(f"a checkout moves to a full SHA, not {revision!r}")
        p = git(checkout.path, "checkout", "--detach", "--force", revision)
        if p.returncode != 0:
            raise ResourceUnavailable(f"checkout {checkout.name} to {revision[:12]}: git checkout exited {p.returncode}")
        git(checkout.path, "clean", "-fdq")
        checkout.revision = revision

    def diff(self, base: str, candidate: str) -> str:
        p = git(self.repo, "diff", "--no-color", f"{base}..{candidate}")
        if p.returncode != 0:
            raise InvariantError(f"git diff {base[:12]}..{candidate[:12]} exited {p.returncode}")
        return p.stdout


class GitMerger:
    """Merges a candidate into `branch` of the repository, in a merge worktree of its own. The outcome is typed from
    git: exit 0 with a new commit is MERGED at that SHA; a non-zero exit with unmerged paths is a CONFLICT naming
    them; anything else raises (the runner flattens it to UNKNOWN, §22)."""

    def __init__(self, repo: str | os.PathLike, branch: str, root: str | os.PathLike) -> None:
        self.repo, self.branch, self.root = str(repo), branch, pathlib.Path(root)

    def base(self) -> str:
        return _sha(self.repo, self.branch)

    def merge(self, candidate: str) -> Merge:
        if not FULL_SHA.fullmatch(candidate):
            raise InvariantError(f"a merge takes a full SHA, not {candidate!r}")
        candidate = _sha(self.repo, candidate)
        tip = self.base()
        path = self.root / f"merge-{tip[:12]}-{candidate[:12]}"
        if path.exists():
            raise RuntimeError(f"merge worktree {path} already exists")
        added = git(self.repo, "worktree", "add", "--detach", str(path), tip)  # detached: the branch may be checked out
        if added.returncode != 0:
            raise RuntimeError(f"merge worktree: git worktree add exited {added.returncode}")
        try:
            merged = git(path, "-c", "user.name=aisef", "-c", "user.email=aisef@localhost", "merge", "--no-ff",
                         "--no-edit", "-m", f"merge {candidate[:12]}", candidate)
            if merged.returncode == 0:
                head = _sha(path, "HEAD")
                moved = git(self.repo, "update-ref", f"refs/heads/{self.branch}", head, tip)
                if moved.returncode != 0:
                    raise RuntimeError(f"branch {self.branch} moved during the merge: not updated")
                return Merge(MergeOutcome.MERGED, head, ())
            unmerged = git(path, "diff", "--name-only", "--diff-filter=U")   # in git's index order
            conflicts = tuple(ln for ln in unmerged.stdout.splitlines() if ln.strip())
            if conflicts:   # the conflicted worktree is removed below; nothing of it reaches the branch
                return Merge(MergeOutcome.CONFLICT, None, conflicts)
            raise RuntimeError(f"git merge exited {merged.returncode} without unmerged paths")
        finally:
            git(self.repo, "worktree", "remove", "--force", str(path))

    def revert(self, merged: str) -> None:
        """Undo the merge commit `merged`: the branch goes back to the merge's first parent, the tip it had before
        (a post-merge regression rolls the merge back, §26; concurrent commits on the branch are kept)."""
        if not FULL_SHA.fullmatch(merged):
            raise InvariantError(f"a revert takes the merge's full SHA, not {merged!r}")
        merged = _sha(self.repo, merged)
        if _sha(self.repo, self.branch) != merged:
            raise Residual(f"branch {self.branch} is not at the merge {merged[:12]}: nothing reverted")
        before = _sha(self.repo, f"{merged}^1")
        p = git(self.repo, "update-ref", f"refs/heads/{self.branch}", before, merged)
        if p.returncode != 0:
            raise Residual(f"branch {self.branch} could not be reset to {before[:12]}")


def commit_all(checkout: str | os.PathLike, message: str, *, author: Sequence[str] = ("-c", "user.name=developer",
                                                                                          "-c", "user.email=dev@localhost")) -> str:
    """Stage and commit everything in a checkout; the new commit's full SHA. A developer capability's usual last step."""
    git(checkout, "add", "-A")
    p = git(checkout, *author, "commit", "-q", "--allow-empty", "-m", message)
    if p.returncode != 0:
        raise RuntimeError(f"git commit exited {p.returncode}")
    return _sha(checkout, "HEAD")
