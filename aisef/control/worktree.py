"""Isolate parallel stories using git worktrees.

Wave partitioning by ``write_scope`` only prevents *file content* collisions.
Three things still clash when multiple stories share a working directory:

* concurrent ``git add`` / ``git commit`` fighting over ``index.lock``;
* concurrent tests fighting over network ports, databases, temp files;
* concurrent dependency installs corrupting ``node_modules`` / venv.

Each story in a wave therefore runs in its own worktree with its own branch.
Worktrees share ``.git`` so creation is fast and disk-cheap.

After a wave, branches are **merged sequentially** into the main branch. See
``merge_story`` for why a conflict here is a signal, not an incident.
Mechanism validated in spike S5 (`docs/SPIKE-REPORT.md`).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from aisef._compat import flock_ex_nb, flock_un

#: Worktree directory, relative to the repo root.
WORKTREE_ROOT = ".aisef/worktrees"

#: Story branch name prefix.
BRANCH_PREFIX = "story/"

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class GitError(RuntimeError):
    """A git command failed."""


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        timeout=30,
    )
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc


def commit_paths(path: Path, message: str, *, paths: list[str] | None = None,
                 exclude: list[str] | None = None) -> bool:
    """Commit remaining uncommitted work in a working tree. False means nothing to commit.

    Stage **only the declared write scope**, not `add -A` (invariant 5).
    `diff-scope` usually already confirmed the tree is within scope, so both
    approaches give the same result — but only when the guard has run. Staging
    by scope is correct even when it hasn't, and that is what the invariant protects.
    """
    if not _git(path, "status", "--porcelain", check=False).stdout.strip():
        return False  # agent already committed everything

    if paths is None:
        _git(path, "add", "-u")
    else:
        specs = [f":(literal){p}" for p in paths]
        staged = set(_git(path, "diff", "--cached", "--name-only", "--no-renames", "-z").stdout.split("\0")) - {""}
        allowed = set(_git(path, "ls-files", "-z", "--", *specs).stdout.split("\0")) - {""} if specs else set()
        allowed.update(p for p in staged if any(
            p == scope.rstrip("/") or p.startswith(scope.rstrip("/") + "/")
            for scope in paths))
        if staged - allowed:
            raise GitError("pre-staged changes outside write scope: " + ", ".join(sorted(staged - allowed)))
        matched = [spec for p, spec in zip(paths, specs, strict=True)
                   if (path / p).exists() or _git(path, "ls-files", "-z", "--", spec).stdout]
        if matched:
            _git(path, "add", "-A", "--", *matched)
    if exclude:
        # F4 / SS-41: paths that were already there before the session opened are PREEXISTING, not the developer's
        # work — unstaged (kept in the tree), never part of the candidate
        _git(path, "reset", "-q", "--", *[f":(literal){e}" for e in exclude], check=False)
    _unstage_tool_artifacts(path)
    if not _git(path, "diff", "--cached", "--name-only", check=False).stdout.strip():
        return False
    _git(path, "commit", "-q", "-m", message)
    return True


def _unstage_tool_artifacts(path: Path) -> None:
    """A scope of `tests` stages `tests/.coverage` along with the tests. The
    coverage data file is the test tool's output, not the story's work
    (D-030): take it back out before the candidate is frozen, so no gate
    ever scores a binary the next run rewrites."""
    from ..harness.guardrails import is_tool_artifact

    staged = [p for p in _git(path, "diff", "--cached", "--name-only", "-z", check=False)
              .stdout.split("\0") if p and is_tool_artifact(p)]
    if staged:
        _git(path, "reset", "-q", "--", *staged)


def main_repo(path: Path | str) -> Path:
    """Main repository root for a given path, even when inside a worktree.

    Stories run in separate worktrees, but evidence and state must be written
    to **a single artifact root** (invariant 2). Otherwise each story writes
    to its own root and the gate reading from the main root sees nothing.
    """
    path = Path(path).resolve()
    proc = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return path
    common = Path(proc.stdout.strip())
    return common.parent if common.name == ".git" else path


class RunOwnedError(RuntimeError):
    pass


@contextmanager
def run_ownership(project: Path | str) -> Iterator[None]:
    lock_path = main_repo(project) / ".aisef" / "run.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as owner:
        try:
            flock_ex_nb(owner.fileno())
        except BlockingIOError:
            raise RunOwnedError(f"another run owns {lock_path.parent.parent}") from None
        try:
            yield
        finally:
            flock_un(owner.fileno())


def safe_slug(story_id: str) -> str:
    """Convert a story id into a safe branch/directory name slug."""
    slug = _SAFE.sub("-", story_id).strip("-")
    if not slug:
        raise ValueError(f"unusable story id: {story_id!r}")
    return slug


@dataclass(frozen=True)
class Worktree:
    story_id: str
    path: Path
    branch: str
    #: Main branch merged in on reconnect, or "" if not needed.
    #: Recorded so readers know which base this worktree stands on.
    refreshed_from: str = ""


@dataclass
class MergeResult:
    story_id: str
    branch: str
    merged: bool
    conflicts: list[str] = field(default_factory=list)
    message: str = ""

    @property
    def scope_was_misdeclared(self) -> bool:
        """A conflict means two stories touched the same region.

        The scheduler only places stories with disjoint ``write_scope`` in
        the same wave, so a merge conflict means the scope was misdeclared.
        """
        return bool(self.conflicts)


#: Client config generated by `compile` that the project may not commit.
CLIENT_CONFIG = (".claude/settings.json", ".opencode")


def _xoa(path: Path) -> None:
    """Remove a generated file or directory; missing is fine."""
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


class WorktreeManager:
    """Create, clean up, and merge story worktrees."""

    # git worktree add races on .git/worktrees metadata under ThreadPoolExecutor
    _create_lock = threading.Lock()

    def __init__(self, repo: Path, *, root: str = WORKTREE_ROOT):
        self.repo = Path(repo).resolve()
        self.root = self.repo / root
        if not (self.repo / ".git").exists():
            raise GitError(f"{self.repo} is not a git repository")

    # ------------------------------------------------------------ create, clean up

    def path_for(self, story_id: str) -> Path:
        return self.root / safe_slug(story_id)

    def branch_for(self, story_id: str) -> str:
        return f"{BRANCH_PREFIX}{safe_slug(story_id)}"

    def has_branch(self, story_id: str) -> bool:
        """Whether the story branch still exists — after the worktree is removed,
        the branch holds the work and is a candidate for re-verification."""
        return self._branch_exists(self.branch_for(story_id))

    def create(self, story_id: str, *, base: str | None = None,
               refresh: bool = True) -> Worktree:
        """Create a worktree for a story. Idempotent: returns existing one if present.

        If the branch already exists, **merge the main branch in before handing
        off to the agent** — unless ``refresh=False``: re-verification (ADR-004
        R13) grades the exact candidate frozen at the story branch HEAD, and a
        merge commit creates a new revision that makes all prior evidence stale.
        Without this, a retried story still stands on the trunk at the point it
        forked: config fixes, tool patches, and work from stories merged in
        earlier waves never arrive. Measured on project `par`:
        `story/STORY-01-01` forked from `e0a6b4e`, the test command patch was
        at `963dae3`, and the story failed due to exactly the bug fixed on main.

        Merge, not rebase: rebase rewrites the agent's commit history, and a
        conflict mid-way through a commit chain is unresolvable.
        """
        path, branch = self.path_for(story_id), self.branch_for(story_id)
        if (path / ".git").exists():
            return self._reuse(story_id, path, branch, base=base, refresh=refresh)
        with self._create_lock:
            if (path / ".git").exists():
                return self._reuse(story_id, path, branch, base=base, refresh=refresh)
            if path.exists():
                shutil.rmtree(path)
                _git(self.repo, "worktree", "prune")

            self._ensure_root()
            exists = self._branch_exists(branch)
            args = ["worktree", "add", "-q"]
            if exists:
                args += [str(path), branch]
            else:
                args += [str(path), "-b", branch]
                if base:
                    args.append(base)
            _git(self.repo, *args)

        # Refresh **first**, then lay the client config down. The other order
        # copies a generated file over a tracked one, and `git merge` then
        # refuses to run at all: "your local changes would be overwritten".
        # Measured on todo/STORY-01-02 2026-09-09 — the merge that brings the
        # trunk's fixes into the story failed while `git merge-tree` showed
        # the branches merge cleanly. The config is re-derived here anyway.
        merged_from = self.refresh(story_id, base=base) if exists and refresh else ""
        self._carry_client_config(path)
        return Worktree(story_id, path, branch, refreshed_from=merged_from)

    def _reuse(self, story_id: str, path: Path, branch: str, *,
               base: str | None, refresh: bool) -> Worktree:
        """A worktree that is already there — refresh it like a new one.

        Skipping the merge here meant a worktree left behind by a **failed**
        run kept its old base for every run after: `dev/serve.py`, config
        fixes and stories merged in earlier waves never arrived, and the story
        failed again on something already fixed on the trunk (measured on
        todo/STORY-01-02 2026-09-09). The merge is a no-op when the trunk has
        not moved, so this costs nothing in the common case.
        """
        merged_from = self.refresh(story_id, base=base) if refresh else ""
        self._carry_client_config(path)   # a reused worktree can hold a stale guard
        return Worktree(story_id, path, branch, refreshed_from=merged_from)

    def _carry_client_config(self, path: Path) -> list[str]:
        """Put the client config `compile` generated into the worktree.

        Claude receives `--settings` explicitly, but OpenCode only reads
        `.opencode/` from its working directory — without copying, guards
        don't reach it. Measured in conformance 2026-09-05: OpenCode C1
        `rm -rf` ran for real, file lost, because the worktree had no plugin.

        **Overwrite**, always. These are generated artifacts ("next run will
        overwrite"), and when a project commits them the worktree checks out
        the committed blob — so a plugin fixed by `aisef compile` never
        reached a single story. Measured on `todo` 2026-09-09: the committed
        copy carried the broken `BIN`, the fixed one sat in the project root
        unused, and every worktree ran unguarded.
        """
        copied = []
        for rel in CLIENT_CONFIG:
            src, dst = self.repo / rel, path / rel
            if not src.exists():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
            copied.append(rel)
        return copied

    def refresh(self, story_id: str, *, base: str | None = None) -> str:
        """Merge the main branch into the story branch. Returns source branch name, or "".

        On conflict, aborts and **raises an error**: a story running on a stale
        trunk works on the wrong base, and hiding that only surfaces the error
        at the end-of-wave merge, far from where it was caused.
        """
        path = self.path_for(story_id)
        base_branch = base or self._current_branch()
        if not base_branch or not path.is_dir():
            return ""
        # Discard our own copy of the generated client config before merging:
        # a worktree reused from an earlier run still carries it, and git
        # refuses to merge over a locally modified tracked file. It is put
        # back immediately after the merge.
        #
        # `git checkout --` restores a **tracked** file and does nothing for
        # an untracked one, which is what these are until the project commits
        # them. The day the project does commit one, every story worktree
        # still holds its untracked copy and git refuses the merge with "the
        # following untracked working tree files would be overwritten" —
        # nothing conflicted, so the message below named no files and told the
        # operator to delete a branch carrying three attempts of committed
        # work (lỗi 123, todo-cli 2026-09-13 on `.claude/settings.json`).
        # Copied back by `sync_client_config` right after.
        for rel in CLIENT_CONFIG:
            if not (path / rel).exists():
                continue
            subprocess.run(["git", "checkout", "--", rel], cwd=path,
                           capture_output=True, timeout=30)
            if _git(path, "ls-files", "--error-unmatch", rel,
                    check=False).returncode != 0:
                _xoa(path / rel)
        # Already contains the main branch tip — no merge needed; avoids
        # creating an empty merge commit on every rerun.
        tip = _git(self.repo, "rev-parse", base_branch, check=False).stdout.strip()
        if tip and _git(
            path, "merge-base", "--is-ancestor", tip, "HEAD", check=False
        ).returncode == 0:
            return ""

        proc = _git(path, "merge", "--no-edit", base_branch, check=False)
        if proc.returncode == 0:
            return base_branch
        conflicting = [
            l.strip()
            for l in _git(path, "diff", "--name-only", "--diff-filter=U",
                          check=False).stdout.splitlines()
            if l.strip()
        ]
        _git(path, "merge", "--abort", check=False)
        if not conflicting:
            # No file is in conflict, so the merge never got that far: git
            # refused up front (untracked file in the way, dirty tree, ...).
            # Advising "delete the branch" here tells the operator to throw
            # away committed work over something the tree can fix — git's own
            # first line says what it actually was.
            ly_do = (proc.stderr or proc.stdout or "").strip().splitlines()
            raise GitError(
                f"{story_id}: git refused to merge `{base_branch}` into the story branch "
                f"before reaching any conflict: "
                + (" / ".join(x.strip() for x in ly_do[:3]) or "no message from git")
                + ". The story branch is fine — clean the worktree "
                f"({path}) and rerun."
            )
        raise GitError(
            f"{story_id}: cannot merge `{base_branch}` into story branch — conflicts in "
            f"{', '.join(conflicting[:5])}. Story branch has diverged too "
            f"far; delete the branch and rerun, or merge manually."
        )

    def _current_branch(self) -> str:
        out = _git(self.repo, "rev-parse", "--abbrev-ref", "HEAD", check=False).stdout.strip()
        return "" if out in ("", "HEAD") else out

    def remove(self, story_id: str, *, delete_branch: bool = False) -> None:
        """Remove the worktree. Does not delete the branch unless requested —
        committed work must not disappear just because the directory is cleaned up."""
        path = self.path_for(story_id)
        if path.exists():
            _git(self.repo, "worktree", "remove", "--force", str(path), check=False)
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
        _git(self.repo, "worktree", "prune", check=False)
        if delete_branch:
            _git(self.repo, "branch", "-D", self.branch_for(story_id), check=False)

    def list_active(self) -> list[str]:
        """Story ids that currently have a worktree."""
        if not self.root.is_dir():
            return []
        return sorted(p.name for p in self.root.iterdir() if p.is_dir())

    @contextmanager
    def temporary(self, sha: str, *, label: str = "qa") -> Iterator[Path]:
        """Temporary **detached** worktree at exactly ``sha``; removed on exit
        from the ``with`` block, even if an exception is raised inside.

        For project-level verification (ADR-005 V6): the tree under test is
        reconstructed from SHA, not the working tree the agent (or human) just
        edited — uncommitted shims like `node_modules/.bin/*`, `pytest.ini`,
        `conftest.py` cannot reach here. No branch is created: nothing to keep
        after verification. Directory is created via ``mkdtemp`` so two calls
        with the same SHA don't collide.
        """
        self._ensure_root()
        path = Path(tempfile.mkdtemp(prefix=f"{label}-{sha[:7]}-", dir=self.root))
        try:
            _git(self.repo, "worktree", "add", "-q", "--detach", str(path), sha)
        except GitError:
            shutil.rmtree(path, ignore_errors=True)
            raise
        try:
            yield path
        finally:
            _git(self.repo, "worktree", "remove", "--force", str(path), check=False)
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
            _git(self.repo, "worktree", "prune", check=False)

    # ------------------------------------------------------------ merging

    def commit_story(
        self, story_id: str, message: str = "", *, paths: list[str] | None = None
    ) -> bool:
        """Commit remaining uncommitted work in a story's worktree.

        Agents are encouraged to commit incrementally, but the harness commits
        whatever is left: merge only sees committed content, so skipping this
        step leaves the story "done" with work that never reaches the main branch.

        Stage **only the story's declared write scope**, not `add -A` (invariant 5).
        `diff-scope` just confirmed the tree is within scope, so both approaches
        give the same result — but only when the guard has run. Staging by scope
        is correct even when it hasn't, and that is what the invariant protects.
        """
        path = self.path_for(story_id)
        if not path.is_dir():
            return False
        return commit_paths(path, message or f"{story_id}: done", paths=paths)

    MERGE_LOCK_TIMEOUT = 120

    @contextmanager
    def _merge_lock(self) -> Iterator[None]:
        """Merge lock — only one machine merges into the main branch at a time."""
        lock_path = self.repo / ".aisef" / "merge.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(lock_path, "w")
        deadline = time.monotonic() + self.MERGE_LOCK_TIMEOUT
        while True:
            try:
                flock_ex_nb(fh.fileno())
                break
            except OSError as err:
                if time.monotonic() >= deadline:
                    fh.close()
                    raise GitError("merge lock timeout — another machine is merging") from err
                time.sleep(0.1)
        try:
            yield
        finally:
            flock_un(fh.fileno())
            fh.close()

    def merge_story(self, story_id: str, *, into: str | None = None,
                    expected_candidate: str | None = None) -> MergeResult:
        """Merge a story branch into the main branch.

        On conflict, **aborts immediately** and returns the list of conflicting
        files. Does not auto-resolve: per the scheduler, two stories in the same
        wave should never touch the same region, so a conflict is evidence that
        ``write_scope`` was misdeclared — needs a human to review the story
        split, not a cleverer merge.

        Merge lock ensures only one machine merges at a time (distributed).
        """
        with self._merge_lock():
            return self._merge_story_inner(story_id, into=into,
                                           expected_candidate=expected_candidate)

    def _merge_story_inner(self, story_id: str, *, into: str | None = None,
                           expected_candidate: str | None = None) -> MergeResult:
        branch = self.branch_for(story_id)
        if expected_candidate is not None:
            actual = _git(self.repo, "rev-parse", branch, check=False).stdout.strip()
            path = self.path_for(story_id)
            from ..harness.ownership import NOT_A_WRITE, classify, porcelain_entries
            dirty = ([p for _, p in porcelain_entries(path) if classify(p) not in NOT_A_WRITE]
                     if path.is_dir() else [])                                # a tool artifact never blocks a merge (SS-17)
            if not expected_candidate or actual != expected_candidate:
                return MergeResult(story_id, branch, False,
                                   message="candidate changed or missing; re-verification required")
            if dirty:
                return MergeResult(story_id, branch, False,
                                   message=f"the story worktree carries uncommitted writes ({', '.join(dirty[:3])}); "
                                           "re-verification required")
        if into:
            _git(self.repo, "checkout", "-q", into)

        proc = _git(self.repo, "merge", "--no-edit", expected_candidate or branch, check=False)
        if proc.returncode == 0:
            return MergeResult(story_id, branch, True, message=proc.stdout.strip())

        conflicts = [
            l.strip()
            for l in _git(self.repo, "diff", "--name-only", "--diff-filter=U", check=False).stdout.splitlines()
            if l.strip()
        ]
        _git(self.repo, "merge", "--abort", check=False)
        return MergeResult(
            story_id,
            branch,
            False,
            conflicts=conflicts,
            message=(proc.stderr or proc.stdout).strip(),
        )

    def merge_wave(self, story_ids: list[str], *, into: str | None = None,
                   candidates: dict[str, str] | None = None) -> list[MergeResult]:
        """Merge an entire wave, **sequentially** in the order given.

        Stops at the first conflict: merging further on top of a conflicted
        tree only makes root-cause analysis harder.
        """
        results: list[MergeResult] = []
        for sid in story_ids:
            r = self.merge_story(sid, into=into,
                                 expected_candidate=candidates.get(sid, "") if candidates is not None else None)
            results.append(r)
            if not r.merged:
                break
        return results

    # ------------------------------------------------------------ internals

    def _ensure_root(self) -> None:
        """Create the worktree directory and **self-exclude it from git**.

        The worktree directory lives inside the repo, so without ignoring it
        every ``git status`` would show an extra ``?? .aisef/`` line — enough
        to break "clean tree after merge abort" checks and easy to accidentally
        commit. A ``.gitignore`` containing ``*`` inside the directory is the
        cleanest self-exclusion, without modifying the project's ``.gitignore``.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        marker = self.root / ".gitignore"
        if not marker.exists():
            marker.write_text("*\n", encoding="utf-8")

    def _branch_exists(self, branch: str) -> bool:
        return _git(
            self.repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False
        ).returncode == 0
