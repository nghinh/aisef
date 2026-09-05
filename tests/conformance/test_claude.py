from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from . import _runner as R


@unittest.skipUnless(R.ENABLED and shutil.which("claude"), "AISDLC_CONFORMANCE=1 và có `claude`")
class TestClaudeHopQuy(unittest.TestCase):
    """Hạng nhất: cột này quyết định phát hành."""

    def test_nam_phep_thu(self):
        run = R.run_client("claude")
        path = R.merge_into_report(run)
        for r in run.results:
            with self.subTest(probe=r.probe):
                self.assertTrue(r.passed, f"{r.probe}: {r.detail}")
        self.assertTrue(path.is_file())
