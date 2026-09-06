from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from . import _runner as R


@unittest.skipUnless(R.ENABLED and shutil.which("opencode"), "AISEF_CONFORMANCE=1 và có `opencode`")
class TestOpenCodeHopQuy(unittest.TestCase):
    """Hạng hai V1 (quyết định 2026-09-05): chạy để biết, ghi vào bảng,
    **không** làm test đỏ — điều kiện phát hành không đọc cột này."""

    def test_nam_phep_thu_ghi_nhan(self):
        run = R.run_client("opencode")
        R.merge_into_report(run)
        print("\n".join(f"  opencode {r.probe} {'✅' if r.passed else '✗'} — {r.detail}"
                        for r in run.results))
