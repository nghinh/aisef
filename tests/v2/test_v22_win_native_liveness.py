"""Windows NATIVE integration for the H2 liveness probe (owner post-gate-3 directive #2).

Unlike test_v21_pl7_session_teardown's WinLivenessDecision (which proves the pure `_win_liveness` decision
off-Windows) and the retargeted seam test (which mocks `pid_alive`), this module calls the REAL Win32
OpenProcess/GetExitCodeProcess through `pid_alive` on a real windows-latest runner. It proves, against the
live kernel, the four properties the owner required:

  1. a live process is NOT misread as GONE,
  2. a genuinely-ended process IS detected as gone,
  3. the probe never terminates anything (no unintended terminate — it asks for QUERY_LIMITED only),
  4. access-denied / protected / ambiguous outcomes still fail CLOSED to alive.

It introduces NO new destructive site: children self-terminate (short sleep or immediate exit) and are reaped
with wait(); the test source calls no kill()/terminate()/unlink(). Skipped on POSIX.
"""
import ctypes
import os
import subprocess
import sys
import unittest

from aisef2.runtime.process_range import (
    _WIN_PROCESS_QUERY_LIMITED_INFORMATION,
    pid_alive,
)


@unittest.skipUnless(os.name == "nt", "native Win32 liveness — windows runner only")
class WinNativeLiveness(unittest.TestCase):
    def test_the_probe_asks_for_query_only_never_terminate(self):
        # Structural half of "no unintended terminate": the access right is QUERY_LIMITED (0x1000), which does
        # NOT include PROCESS_TERMINATE (0x0001). A handle without terminate rights cannot kill.
        self.assertEqual(_WIN_PROCESS_QUERY_LIMITED_INFORMATION, 0x1000)
        self.assertFalse(_WIN_PROCESS_QUERY_LIMITED_INFORMATION & 0x0001,
                         "the probe must not request PROCESS_TERMINATE")

    def test_a_live_process_is_alive_and_the_probe_does_not_terminate_it(self):
        # (1) live is not read gone, and (3) the probe does not terminate a live process.
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
        try:
            self.assertTrue(pid_alive(p.pid), "a live process read as gone (native OpenProcess/STILL_ACTIVE)")
            self.assertIsNone(p.poll(), "the read-only probe terminated a live process")
            # behavioural confirmation the probe left the kernel view intact:
            self.assertTrue(pid_alive(p.pid), "second probe disagrees with the first on a still-live process")
        finally:
            p.wait(timeout=30)  # self-terminates at 5s; no kill()

    def test_a_genuinely_ended_process_is_detected_as_gone(self):
        # (2) a process that has exited reads gone. We keep the Popen handle open so the PID is NOT recycled:
        # OpenProcess(pid) then succeeds and GetExitCodeProcess returns the real exit code (0, != STILL_ACTIVE
        # 259) -> _win_liveness concludes gone deterministically, with no PID-reuse race.
        p = subprocess.Popen([sys.executable, "-c", ""])  # exits immediately, code 0
        p.wait(timeout=30)
        self.assertEqual(p.returncode, 0)
        self.assertFalse(pid_alive(p.pid), "an exited process still read as alive (native exit-code path)")

    def test_a_protected_process_fails_closed_to_alive(self):
        # (4) access-denied / protected / ambiguous -> alive. PID 4 (System) is always alive and is the canonical
        # protected process: whether OpenProcess(4) is granted (-> STILL_ACTIVE) or denied (ERROR_ACCESS_DENIED
        # 5, != 87) the only correct answer is alive. This is deterministic regardless of runner integrity.
        self.assertTrue(pid_alive(4), "System (PID 4) must never read gone")

        # Best-effort NATIVE observation of a real access-denied handle, to prove fail-closed on a genuinely
        # denied OpenProcess, not only on the pure decision. Enumerate a bounded low-PID range with raw Win32 —
        # NOT process_table(), which shells out to POSIX `ps` (by design it fails on Windows; H1 catches that in
        # production). Fully guarded: this observation is best-effort and must never error the test — the
        # pid_alive(4) anchor above is the deterministic proof.
        # ponytail: access-denied reachability depends on runner integrity — observe when present, else document.
        observed_denied = None
        try:
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            from ctypes import wintypes
            k.OpenProcess.restype = wintypes.HANDLE
            k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            k.CloseHandle.argtypes = [wintypes.HANDLE]
            for pid in range(1, 2048):
                ctypes.set_last_error(0)
                h = k.OpenProcess(_WIN_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                if h:
                    k.CloseHandle(h)
                    continue
                if ctypes.get_last_error() == 5:  # ERROR_ACCESS_DENIED: a live process we may not fully query
                    observed_denied = pid
                    break
        except Exception as e:  # best-effort only — never fail the test on the optional observation
            print(f"win-native: access-denied scan skipped ({type(e).__name__}: {e})")
        if observed_denied is not None:
            self.assertTrue(pid_alive(observed_denied),
                            f"a live but access-denied pid {observed_denied} read as gone (fail-closed broken)")
        else:
            print("win-native: no access-denied handle reachable on this runner; "
                  "fail-closed-on-denied remains pinned by WinLivenessDecision (pure + mutation-proven)")


if __name__ == "__main__":
    unittest.main()
