"""One answer to "whose path is this" (F4 / INV-I.1, INV-I.2).

Every consumer that used to keep its own skip list — the guard's ``changed_files``, the attempt's tree snapshot,
retry hygiene, the candidate freeze, the merge dirt check — asks ``classify`` instead. Porcelain alone never
determines blame: a dirty path is the DEVELOPER's when a session of this story wrote it, PREEXISTING when it was
already there before the session opened, VERIFIER / CLIENT_GENERATED / HARNESS when a tool, the client or the harness
produced it, and EXTERNAL_UNATTRIBUTED when nobody on record did — and that last class is stated by name and never
deleted automatically (owner rule; D-034).
"""
from __future__ import annotations

import subprocess
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Iterable


class Ownership(str, Enum):
    HARNESS = "HARNESS"                          # the harness's own records and config
    VERIFIER = "VERIFIER"                        # artifacts of tools the harness ran; vendor trees
    CLIENT_GENERATED = "CLIENT_GENERATED"        # files the client (Claude Code, OpenCode) writes for itself
    DEVELOPER = "DEVELOPER"                      # written by a session of this story
    PREEXISTING = "PREEXISTING"                  # already dirty / present before the session opened
    EXTERNAL_UNATTRIBUTED = "EXTERNAL_UNATTRIBUTED"   # dirty, and no session of this story on record for it


#: Files the CLIENT writes for itself inside the project — never a story change (SS-38).
CLIENT_GENERATED_PATHS = (".claude/settings.json", ".claude/settings.local.json")
CLIENT_GENERATED_PREFIXES = (".opencode/",)

NOT_A_WRITE = (Ownership.HARNESS, Ownership.VERIFIER, Ownership.CLIENT_GENERATED)


def _norm(rel: str) -> str:
    return PurePosixPath(rel.replace("\\", "/")).as_posix().strip("/")


def _within(path: str, scope: str) -> bool:
    p, s = PurePosixPath(_norm(path)), PurePosixPath(_norm(scope))
    return p == s or s in p.parents


def porcelain_entries(root: Path | str, *, untracked: bool = True) -> list[tuple[str, str]]:
    """``(status, path)`` for every entry of ``git status --porcelain -z``. A rename or copy carries the ORIGINAL
    path as a second NUL field — it is consumed here, never returned as a phantom path (SS-35)."""
    args = ["git", "status", "--porcelain", "-z"] + (["--untracked-files=all"] if untracked else [])
    try:
        proc = subprocess.run(args, cwd=str(root) or ".", capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    fields = proc.stdout.split("\0")
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(fields):
        e = fields[i]
        i += 1
        if len(e) < 4:
            continue
        code, path = e[:2], e[3:]
        out.append((code, _norm(path)))
        if "R" in code or "C" in code:
            i += 1                                # the original path travels as the next field
    return out


def dirty_paths(root: Path | str) -> list[str]:
    return [p for _, p in porcelain_entries(root)]


def classify(rel: str, *, baseline: Iterable[str] = (), session_writes: Iterable[str] = (),
             scope: Iterable[str] = ()) -> Ownership:
    """Ownership of one dirty/untracked path. ``baseline``: paths dirty or present before the session opened;
    ``session_writes``: paths the story's sessions are on record as writing (guard ``file_change`` evidence,
    attempt snapshots); ``scope``: the story's write scope — a changed path inside it that was not there before
    the session is the developer's."""
    from .guardrails import HARNESS_OWNED, VENDOR_PATHS, is_tool_artifact

    rel = _norm(rel)
    if rel in CLIENT_GENERATED_PATHS or rel.startswith(CLIENT_GENERATED_PREFIXES):   # before HARNESS: `.claude/` is harness-copied,
        return Ownership.CLIENT_GENERATED                                              # its local settings are the client's
    if rel in HARNESS_OWNED or any(_within(rel, h) for h in HARNESS_OWNED) or rel.startswith(".aisef/") or rel == ".aisef":
        return Ownership.HARNESS
    parts = PurePosixPath(rel).parts
    if is_tool_artifact(rel) or any(part in VENDOR_PATHS for part in parts) or rel.endswith(".pyc"):
        return Ownership.VERIFIER
    # the REST of `_bmad-output` (PRD, architecture, visual contract) is not harness-owned: an agent sneaking edits
    # there while writing code must stay visible (guard docstring; tests/test_guardrails.py::TestDiffScope)
    base = {_norm(b) for b in baseline}
    if rel in base:
        return Ownership.PREEXISTING
    if rel in {_norm(w) for w in session_writes}:
        return Ownership.DEVELOPER
    if any(_within(rel, s) for s in scope):
        return Ownership.DEVELOPER
    return Ownership.EXTERNAL_UNATTRIBUTED


def is_write(rel: str) -> bool:
    """Could this path be somebody's WRITE at all (not harness, tool or client output)?"""
    return classify(rel) not in NOT_A_WRITE
