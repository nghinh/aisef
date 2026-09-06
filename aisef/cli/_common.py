"""Mảnh dùng chung của bộ lệnh: mã thoát, gốc artifact, kho duyệt/trạng
thái, adapter client, và bộ chuyển tham số tên cổng.

Mọi module lệnh khác nhập từ đây, nên file này không được nhập ngược lại
chúng — giữ đồ thị nhập một chiều.
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

#: Ký hiệu trạng thái cổng, đủ để đọc lướt.
_GATE_MARK = {
    Status.APPROVED: "✅",
    Status.PENDING: "⏳",
    Status.CHANGES_REQUESTED: "✗",
    Status.STALE: "⚠️",
}


def _artifact_root(args) -> Path:
    """Gốc artifact — **một** gốc cho cả dự án (bất biến 2).

    Agent chạy trong worktree của story, nên `--project .` ở đó trỏ vào
    worktree. Ghi bằng chứng vào đấy thì cổng đọc ở gốc chính không thấy
    gì, và story "chưa từng chạy test" dù nó vừa chạy.
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
        raise argparse.ArgumentTypeError(f"cổng không hợp lệ: {value}. Hợp lệ: {valid}")


def _client(args):
    """Adapter đã kiểm tên và tình trạng cài đặt. None nếu không dùng được."""
    from ..clients.compile import ADAPTERS

    if args.client not in ADAPTERS:
        print(f"✗ client không hỗ trợ: {args.client}", file=sys.stderr)
        return None, EXIT_USAGE
    adapter = ADAPTERS[args.client]()
    if not adapter.available():
        print(f"✗ chưa cài {args.client} trên máy này", file=sys.stderr)
        return None, EXIT_NOT_READY
    return adapter, EXIT_OK
