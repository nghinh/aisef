"""Shared CLI utilities: exit codes, artifact root, approval/state stores,
client adapter, and gate argument converter.

All command modules import from here; this file must not import back
from them — keep the import graph one-directional.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..control.approvals import GATE_ORDER, ApprovalStore, Gate, Status
from ..control.state import StateStore


ARTIFACT_ROOT = "_bmad-output"

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_NOT_READY = 2

_GATE_MARK = {
    Status.APPROVED: "✅",
    Status.PENDING: "⏳",
    Status.CHANGES_REQUESTED: "✗",
    Status.STALE: "⚠️",
}


def _artifact_root(args) -> Path:
    """Artifact root — one root per project (invariant 2).

    Agents run inside story worktrees, so `--project .` there points at
    the worktree. Writing evidence there means the gate reading from the
    main repo root sees nothing.
    """
    from ..control.worktree import main_repo

    return main_repo(args.project) / ARTIFACT_ROOT


def _approvals(args) -> ApprovalStore:
    return ApprovalStore(_artifact_root(args))


def _state(args) -> StateStore:
    return StateStore(_artifact_root(args))


def _gate_arg(value: str) -> Gate:
    try:
        return Gate(value)
    except ValueError:
        valid = ", ".join(g.value for g in GATE_ORDER)
        raise argparse.ArgumentTypeError(f"invalid gate: {value}. Valid: {valid}") from None


def _ensure_git(project: str | Path) -> int | None:
    """Check git readiness; return exit code on failure, None on success."""
    import subprocess

    root = Path(project)
    if not (root / ".git").exists():
        subprocess.run(["git", "init"], cwd=root, capture_output=True)
        print(f"  git init → {root}")

    def _cfg(key: str) -> str:
        r = subprocess.run(
            ["git", "config", key], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return r.stdout.strip()

    if not _cfg("user.name") or not _cfg("user.email"):
        print(
            "✗ git user.name / user.email not configured for this repo.\n"
            "  Run:  git config user.name 'Your Name'\n"
            "        git config user.email 'you@example.com'",
            file=sys.stderr,
        )
        return EXIT_USAGE

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if head.returncode != 0:
        print(
            "✗ no commits yet — aisef needs at least one commit.\n"
            "  Run:  git add . && git commit -m 'initial'",
            file=sys.stderr,
        )
        return EXIT_USAGE
    return None


def _client(args):
    """Validated client adapter. Returns None if unavailable."""
    from ..clients.compile import ADAPTERS

    if args.client not in ADAPTERS:
        print(f"✗ unsupported client: {args.client}", file=sys.stderr)
        return None, EXIT_USAGE
    adapter = ADAPTERS[args.client]()
    if not adapter.available():
        print(f"✗ {args.client} is not installed on this machine", file=sys.stderr)
        return None, EXIT_NOT_READY
    return adapter, EXIT_OK
