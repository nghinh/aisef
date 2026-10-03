"""The real workspace and merger: git worktrees the story owns as `StoryScope` resources, and a merger whose outcome is
typed from git's exit status and its unmerged-path list — never from stderr text (§26, V2-005). Every git the runner
starts runs without background maintenance, so nothing writes into a checkout after its release began.

Deletion authority (INV-MUTATION-AUTHORITY): nothing here removes a path by name. A checkout is removed by git, from
git's own registry of the worktree it added; a scratch directory is removed by the `TemporaryDirectory` handle that
created it. A directory that survives its release is a residual, reported, never forced."""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import tempfile
from typing import Sequence

from aisef2.errors import InvariantError
from aisef2.journal.format2 import ResourceKind as K
from aisef2.orchestrate.adapters import Merge, MergeOutcome, ResourceUnavailable
from aisef2.probe.protocol import FULL_SHA
from aisef2.runtime.story_scope import Residual

#: Settings every git the runner starts runs under, at command scope (above every configuration file): no background
#: maintenance, and — V2.0 release charter B4 — nothing a configuration could make git execute: no fsmonitor, no hook
#: (the hook path is the null device), no signing program; line endings checked out as committed on every platform.
_FORCED = (("maintenance.auto", "false"), ("gc.auto", "0"), ("core.fsmonitor", "false"), ("core.hooksPath", os.devnull),
           ("commit.gpgSign", "false"), ("tag.gpgSign", "false"), ("core.autocrlf", "false"))
_NO_BACKGROUND_GIT = {"GIT_CONFIG_COUNT": str(len(_FORCED)),
                      **{f"GIT_CONFIG_{part}_{i}": kv[j] for i, kv in enumerate(_FORCED) for j, part in enumerate(("KEY", "VALUE"))}}
#: B4: neither the system's nor the operator's global configuration is read; and no variable of the caller's
#: environment that would redirect git to another repository, reconfigure it, or name a program for it to run reaches it
_ISOLATED_GIT = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0", **_NO_BACKGROUND_GIT}
_GIT_ENV_DROPPED = re.compile(r"GIT_(CONFIG.*|DIR|WORK_TREE|COMMON_DIR|INDEX_FILE|OBJECT_DIRECTORY|ALTERNATE_OBJECT_DIRECTORIES"
                              r"|NAMESPACE|CEILING_DIRECTORIES|EXTERNAL_DIFF|DIFF_OPTS|SSH|SSH_COMMAND|EDITOR|SEQUENCE_EDITOR|PAGER"
                              r"|ASKPASS|EXEC_PATH|TEMPLATE_DIR|PROXY_COMMAND|REPLACE_REF_BASE|NO_REPLACE_OBJECTS|ATTR_SOURCE)")
#: B4: the repository's own configuration (local and worktree scope) may hold only these inert keys — a filter, a diff or
#: merge driver, an include, a helper, a hook path, a worktree redirection, a submodule command: anything else is
#: refused before git runs there (an allowlist: a key git adds later is refused until it is named here)
INERT_KEY = re.compile(r"core\.(repositoryformatversion|filemode|bare|logallrefupdates|ignorecase|precomposeunicode|symlinks"
                       r"|autocrlf|eol|safecrlf|checkstat|trustctime|quotepath|untrackedcache)"
                       r"|user\.(name|email)|extensions\.(worktreeconfig|objectformat)|init\.defaultbranch"
                       r"|branch\..+\.(remote|merge|rebase)|remote\.[^.]+\.(url|fetch)|(gc|maintenance|color|advice|status|log|i18n"
                       r"|index|pack)\.[a-z0-9.]+|merge\.conflictstyle|pull\.(rebase|ff)|fetch\.prune|(commit|tag)\.gpgsign")
REFUSED = 128


def _env() -> dict:
    return {**{k: v for k, v in os.environ.items() if not _GIT_ENV_DROPPED.fullmatch(k)}, **_ISOLATED_GIT}


def config_problems(repo: str | os.PathLike) -> list[str]:
    """The keys of the repository's own configuration at `repo` that are not inert (B4). Reading a configuration
    executes nothing; includes are listed, never followed."""
    p = subprocess.run(["git", "-C", str(repo), "config", "--list", "--show-scope", "--no-includes", "-z"],
                       capture_output=True, env=_env())
    if p.returncode != 0:
        return []       # not a repository (yet): the command itself says so
    parts = p.stdout.decode("utf-8", "replace").split("\0")
    keys = [entry.split("\n", 1)[0] for scope, entry in zip(parts[0::2], parts[1::2], strict=False) if scope in ("local", "worktree")]
    return sorted({k for k in keys if not INERT_KEY.fullmatch(k.lower())})


def git(repo: str | os.PathLike, *args: str) -> subprocess.CompletedProcess:
    """git in `repo` under the isolated configuration; a repository whose own configuration holds a key that is not
    inert is refused — nothing runs, and the result says why with exit status REFUSED (B4)."""
    bad = config_problems(repo)
    if bad:
        return subprocess.CompletedProcess(["git", "-C", str(repo), *args], REFUSED, "",
                                           f"refused: the repository configuration at {repo} names {', '.join(bad)} (not inert)")
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, encoding="utf-8", errors="replace", env=_env())


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
        gitfile = self.path / ".git"
        #: B4: the gitfile as git wrote it at `worktree add` — a worktree whose gitfile now points elsewhere is refused
        self.gitfile = gitfile.read_bytes() if gitfile.is_file() else None

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
        gitfile = checkout.path / ".git"
        if checkout.gitfile is None or not gitfile.is_file() or gitfile.is_symlink() or gitfile.read_bytes() != checkout.gitfile:
            raise ResourceUnavailable(f"checkout {checkout.name}: its gitfile is not the one git wrote (B4): not moved")
        p = git(checkout.path, "checkout", "--detach", "--force", revision)
        if p.returncode != 0:
            raise ResourceUnavailable(f"checkout {checkout.name} to {revision[:12]}: git checkout exited {p.returncode}")
        # B6: ignored files (-x) and nested repositories (-ff) go too — nothing a run left survives into the next revision
        c = git(checkout.path, "clean", "-ffdxq")
        if c.returncode != 0:
            raise ResourceUnavailable(f"checkout {checkout.name} at {revision[:12]}: git clean exited {c.returncode}")
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
