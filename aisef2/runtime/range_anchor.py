"""The anchor of a process range (P4-LIFETIME-SEMANTICS.md §3). Run as a script by `process_range`; stdlib only.

It is the controller's own child and the leader of the range's session and process group (POSIX), or the first member
of the range's job (Windows). The controller does not reap it until the range is disposed, so the group id cannot be
reused while the controller can still signal it.

Protocol. stdin (control): one JSON request line {argv, cwd, env}, then `GO` (the controller has made it a member of
its job), later `EXIT`. stdout (report): `STARTED <pid>`, then `EXITED <returncode>` — or `SPAWN_FAILED <error>`.
The target inherits this process's stderr as its stdout and stderr, and gets no stdin.

Reaping (POSIX): the anchor reaps every child but the target, as init would — on Linux it is a subreaper, so the
range's orphans become its children, and an unreaped one is a zombie that still answers kill(pid, 0).

Watchdog: end of file on stdin means the controller is gone. On POSIX the anchor kills its own group (itself
included); on Windows the controller's job handle closed with it and the job killed every member.
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time


def _say(line: str) -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _die() -> None:
    if os.name == "posix":
        os.killpg(os.getpgrp(), signal.SIGKILL)
    os._exit(1)


def _reap_adopted(target: int, poll_s: float = 0.02) -> None:
    """POSIX: reap every child except the target, as init would. On Linux the anchor is a subreaper, so the range's
    orphans become its children; one left unreaped is a zombie that still answers kill(pid, 0) and keeps its group
    signalable. The target is never reaped here: its own wait reports its status (EXITED)."""
    if not hasattr(os, "waitid"):
        return  # Windows: the job kills and closes every member; nothing re-parents here
    while True:
        try:
            info = os.waitid(os.P_ALL, 0, os.WEXITED | os.WNOWAIT)  # blocks until a child can be waited for
        except ChildProcessError:
            info = None  # no child now
        if info is None or info.si_pid == target:
            time.sleep(poll_s)
            continue
        try:
            os.waitpid(info.si_pid, 0)
        except ChildProcessError:
            pass  # reaped meanwhile


def _subreaper() -> None:
    """Linux: become the child subreaper, so an escaped orphan re-parents here, where the controller sees it."""
    if not sys.platform.startswith("linux"):
        return
    try:
        import ctypes
        ctypes.CDLL(None).prctl(36, 1, 0, 0, 0)  # PR_SET_CHILD_SUBREAPER
    except (OSError, AttributeError):
        pass  # escaped orphans then re-parent to init, out of the controller's sight


def main() -> None:
    if os.name == "posix":
        # handlers, not SIG_IGN: a caught signal reverts to its default in the target, an ignored one would not
        signal.signal(signal.SIGINT, lambda *_: None)
        signal.signal(signal.SIGTERM, lambda *_: None)
        _subreaper()
    request = sys.stdin.readline()
    if not request or sys.stdin.readline().strip() != "GO":
        _die()
    req = json.loads(request)
    try:
        proc = subprocess.Popen(req["argv"], cwd=req.get("cwd"), env=req.get("env"), stdin=subprocess.DEVNULL,
                                stdout=sys.stderr, stderr=sys.stderr)
    except OSError as e:
        _say(f"SPAWN_FAILED {type(e).__name__}: {e}")
    else:
        _say(f"STARTED {proc.pid}")
        threading.Thread(target=lambda: _say(f"EXITED {proc.wait()}")).start()  # the anchor ends by os._exit only
        threading.Thread(target=_reap_adopted, args=(proc.pid,)).start()
    while True:
        line = sys.stdin.readline()
        if not line:
            _die()
        if line.strip() == "EXIT":
            os._exit(0)


if __name__ == "__main__":
    main()
