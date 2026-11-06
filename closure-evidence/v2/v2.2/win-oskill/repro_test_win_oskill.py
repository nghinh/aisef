"""FINDING-WIN-OSKILL-001 — Windows reproduction test (STAGED, owner decision #2).

NOT WIRED INTO THE SUITE. This file lives under closure-evidence/ on purpose so Windows CI stays green
before the fix (owner decision #6): on unfixed CPython <= 3.12 this test turns Windows CI RED by letting the
real `os.kill(pid, 0)` terminate a live process. It is written to be MOVED INTO tests/v2/ together with the
safe fix (FINDING-WIN-OSKILL-001-SAFE-FIX-PLAN.md §7, Option A). After the fix it passes.

What it pins: `aisef2/app/client.py:46` `_is_gone` probes liveness with a bare `os.kill(pid, 0)`, documented
as "existence probe only; no signal is ever sent." On Windows `os.kill(pid, 0)` is destructive (it routes to a
Ctrl+C console event and/or TerminateProcess(handle, 0)), so the "probe" KILLS a live process. On Windows
`process_table()` raises (no `ps`), so `_is_gone` takes exactly the `os.kill` fallback branch — the hazard.

Run manually on a Windows host from the repo root:  python -m pytest closure-evidence/v2/v2.2/win-oskill/repro_test_win_oskill.py
(It self-skips off Windows.)
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import client  # noqa: E402


class _Proc:
    """Minimal stand-in for process_range.Proc. On Windows process_table() raises, so `_is_gone` never reads
    `.created`; it is here only to match the (pid, proc) call shape."""
    created = None


class WinOsKillIsDestructive(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "os.kill(pid, 0) is a safe POSIX probe off Windows")
    def test_is_gone_must_not_terminate_a_live_escapee_on_windows(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            self.assertIsNone(child.poll(), "precondition: the child must be alive before the probe")

            gone = client._is_gone(child.pid, _Proc())

            time.sleep(0.2)  # give a delivered Ctrl+C / TerminateProcess time to land
            self.assertIsNone(
                child.poll(),
                "FINDING-WIN-OSKILL-001: _is_gone terminated a live process on Windows — os.kill(pid, 0) is "
                "not a probe there (it routes to TerminateProcess / a Ctrl+C console event). The fix must use a "
                "read-only existence check (pid_alive pattern: OpenProcess + GetExitCodeProcess).",
            )
            self.assertFalse(gone, "a live process must not be reported as 'provably gone'")
        finally:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
