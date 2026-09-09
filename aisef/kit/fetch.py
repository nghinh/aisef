"""Fetch skill source repos to the local machine at the exact commit pinned in the catalog.

Previously `aisef setup` required a pre-cloned ``references/`` directory next
to the project. That only worked when the framework ran from a source checkout:
users who installed via ``pip install aisef`` had no way to obtain that
directory, and ``setup`` failed on the first line.

Skill sources belong to the **framework**, not the target project -- so they
live in the user's cache, shared across all projects. Each source is fetched
at the exact ``commit`` the catalog pins: if skills change mid-run the install
plan silently changes too, and builds lose reproducibility.
"""

from __future__ import annotations

import os
import shutil
import sys
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .catalog import Catalog, Source

#: Environment variable to override the source directory (CI, offline machines).
ENV_REFS = "AISEF_REFERENCES"

CLONE_TIMEOUT = 300


def default_root() -> Path:
    """Skill source location: user cache, not inside the project."""
    if env := os.environ.get(ENV_REFS):
        return Path(env).expanduser().resolve()
    base = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
    return Path(base).expanduser().resolve() / "aisef" / "references"


@dataclass
class FetchReport:
    fetched: list[str] = field(default_factory=list)
    already: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed

    def summary(self) -> str:
        dong = []
        for i in self.fetched:
            dong.append(f"  ✅ fetched  {i}")
        for i in self.already:
            dong.append(f"  ○ already  {i}")
        for i, ly_do in self.failed:
            dong.append(f"  ✗ failed   {i} — {ly_do}")
        return "\n".join(dong) or "  (no sources to fetch)"


def _dir_of(source: Source, root: Path) -> Path:
    """Destination directory for a source, matching how `Source.roots` resolves paths."""
    return Path(root).parent / source.local_path


def _at_commit(d: Path, commit: str) -> bool:
    try:
        r = subprocess.run(
            ["git", "-C", str(d), "rev-parse", "HEAD"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0 and r.stdout.strip() == commit


def _clone(source: Source, dest: Path) -> str:
    """Shallow-clone a single commit. Return empty string on success, error message otherwise."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".dang-lay")
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        for cmd in (
            ["git", "init", "--quiet", str(tmp)],
            ["git", "-C", str(tmp), "remote", "add", "origin", source.repo],
            ["git", "-C", str(tmp), "fetch", "--quiet", "--depth", "1",
             "--no-tags", "origin", source.commit],
            ["git", "-C", str(tmp), "checkout", "--quiet", "FETCH_HEAD"],
        ):
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=CLONE_TIMEOUT)
            if r.returncode != 0:
                error = (r.stderr or r.stdout).strip().splitlines()
                return error[-1] if error else f"git exited {r.returncode}"
    except subprocess.TimeoutExpired:
        return f"exceeded {CLONE_TIMEOUT}s"
    except OSError as e:
        return str(e)
    _remove_tree(dest)
    tmp.replace(dest)
    return ""


def _remove_tree(path: Path) -> None:
    """Delete a directory tree, including the read-only files git leaves.

    Windows refuses to unlink a read-only file, and a fresh clone's
    `.git/objects` is full of them: `aisef setup` failed with
    `PermissionError [WinError 5] Access is denied` while replacing a cached
    reference repo. POSIX does not care, which is why this went unnoticed.
    """
    def _force(func, target, _exc):
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except OSError:
            pass

    if not path.exists():
        return
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_force)
    else:
        shutil.rmtree(path, onerror=_force)


def ensure(
    root: Path | str | None = None,
    *,
    catalog: Catalog | None = None,
    only: list[str] | None = None,
) -> FetchReport:
    """Ensure all catalog sources are present at `root` at the pinned commit.

    Sources already at the correct commit are left untouched -- calling
    repeatedly costs nothing. A failed source does not kill the rest:
    `setup` can still install what was fetched and reports what is missing.
    """
    root = Path(root) if root is not None else default_root()
    cat = catalog or Catalog.load()
    report = FetchReport()
    for source in cat.sources:
        if only and source.id not in only:
            continue
        dest = _dir_of(source, root)
        if _at_commit(dest, source.commit):
            report.already.append(source.id)
            continue
        error = _clone(source, dest)
        (report.fetched if not error else report.failed).append(
            source.id if not error else (source.id, error)
        )
    return report
