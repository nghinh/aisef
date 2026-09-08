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
        raise argparse.ArgumentTypeError(f"invalid gate: {value}. Valid: {valid}")


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
