"""WP-4.2 — measured process-range emptiness (RFC §17.1; P4-LIFETIME-SEMANTICS.md §3). Kill set for
`process_range.py`. Real processes on every OS the suite runs on (Linux, macOS, Windows CI).

D-024 (red before / green after), PROC-OWN-1 (the controller dies or times out: nothing owned survives outside the
range) and PROC-OWN-2 (after disposal, nothing is ever signalled again). WIN-PID-1/2: test_process_table.py.
"""

import json
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.journal.format2 import ResourceKind as K  # noqa: E402
from aisef2.runtime import process_range as pr  # noqa: E402
from aisef2.runtime.process_range import Proc, ProcessRange, RangeNotEmpty  # noqa: E402
from aisef2.runtime.story_scope import Directory, StoryScope  # noqa: E402
from tests.v2.p4.world import Journal2, emitter, released  # noqa: E402

PY = sys.executable
POSIX = os.name == "posix"
FAST = {"grace_s": (1.0, 1.0), "wait_s": 10.0}


def alive(pid: int) -> bool:
    """Is `pid` a live (non-zombie) process now? Test-side only: the range never uses a pid to decide ownership."""
    if POSIX:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return pid in pr.process_table()
    import ctypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = ctypes.c_void_p
    h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    try:
        k.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(code))
    finally:
        k.CloseHandle(ctypes.c_void_p(h))
    return code.value == 259  # STILL_ACTIVE


def gone(pid: int, within: float = 10.0) -> bool:
    deadline = time.monotonic() + within
    while alive(pid):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.05)
    return True


def lingering(pid_file: pathlib.Path, seconds: float = 60.0, writes_into: pathlib.Path | None = None) -> str:
    """A target that starts a grandchild and exits at once; the grandchild writes its pid, then sleeps or keeps
    writing into a directory (recreating it) for `seconds`."""
    work = (f"d = pathlib.Path({str(writes_into)!r})\n"
            f"end = time.time() + {seconds}\n"
            "while time.time() < end:\n"
            "    try:\n"
            "        d.mkdir(parents=True, exist_ok=True)\n"
            "        (d / f'f{time.time_ns()}').write_text('x')\n"
            "    except OSError:\n"
            "        pass  # Windows: a write into a directory being removed fails; a real writer keeps going\n"
            "    time.sleep(0.005)\n") if writes_into else f"time.sleep({seconds})\n"
    grandchild = f"import os, pathlib, time\npathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()))\n" + work
    return (f"import subprocess, sys, time, pathlib\n"
            f"subprocess.Popen([sys.executable, '-c', {grandchild!r}])\n"
            f"p = pathlib.Path({str(pid_file)!r})\n"
            "while not p.exists() or not p.read_text():\n"
            "    time.sleep(0.01)\n")


def read_pid(path: pathlib.Path) -> int:
    deadline = time.monotonic() + 20
    while not (path.exists() and path.read_text().strip()):
        if time.monotonic() > deadline:
            raise AssertionError(f"{path} was never written")
        time.sleep(0.01)
    return int(path.read_text())


class Range(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory(prefix="aisef2-range-")
        self.addCleanup(self._d.cleanup)
        self.dir = pathlib.Path(self._d.name)

    def range(self, code, **kw):
        r = ProcessRange("r", [PY, "-c", code], **{**FAST, **kw}).start()
        self.addCleanup(lambda: r.release() if not r._reaped else None)
        return r

    def test_a_normal_tree_is_reaped_and_measured_empty(self):
        pid_file = self.dir / "g.pid"
        r = self.range(lingering(pid_file))
        self.assertEqual(r.wait(20), 0)  # the direct child is done ...
        grandchild = read_pid(pid_file)
        self.assertEqual([p.pid for p in r.members()], [grandchild])  # ... and the range is not empty
        self.assertIs(r.kind, K.PROCESS_RANGE)
        r.release()
        self.assertEqual(r.members(), [])
        self.assertTrue(gone(grandchild))
        self.assertEqual([s["stage"] for s in r.ledger], ["cooperative"] if POSIX else ["terminate_job"])
        self.assertEqual(sorted(r.ledger[0]), ["at", "signal", "stage"])
        self.assertIsInstance(r.ledger[0]["at"], float)  # when it was sent, on the monotonic clock
        self.assertEqual(r.returncode, 0)
        self.assertTrue(r._anchor.stdin.closed and r._anchor.stdout.closed)  # the pipes go with the anchor

    @unittest.skipUnless(POSIX, "zombies are a POSIX state")
    def test_an_orphan_the_range_adopts_is_reaped_when_it_dies(self):
        """Linux: the anchor is a subreaper, so the grandchild re-parents to it when the target exits; killed, it
        must be reaped at once — a zombie still answers kill(pid, 0) and keeps its group signalable (CI, cfe14c0)."""
        pid_file = self.dir / "g.pid"
        r = self.range(lingering(pid_file))
        grandchild = read_pid(pid_file)
        self.assertEqual(r.wait(20), 0)  # its parent is gone: the grandchild is an orphan now
        os.kill(grandchild, signal.SIGKILL)
        deadline = time.monotonic() + 10
        while True:
            try:
                os.kill(grandchild, 0)
            except ProcessLookupError:
                break  # reaped: no zombie left
            self.assertLess(time.monotonic(), deadline, f"{grandchild} is still a process (a zombie nobody reaps)")
            time.sleep(0.05)
        r.release()

    def test_a_tree_that_exits_by_itself_is_released_without_a_signal(self):
        self.assertIsNone(ProcessRange("unstarted", [PY]).anchor_returncode)
        r = self.range("import time; time.sleep(0.1)")
        self.assertEqual(r.wait(20), 0)
        r.release()
        self.assertEqual((r.ledger, r.members()), ([], []))
        self.assertEqual(r.wait(0), 0)  # the returncode is kept
        self.assertEqual(r.anchor_returncode, 0)  # told to EXIT: a clean end

    def test_a_running_target_is_stopped_graceful_first(self):
        r = self.range("import time\nend = time.time() + 120\nwhile time.time() < end: time.sleep(0.05)")
        self.assertIsNone(r.wait(0.3))
        r.release()
        self.assertEqual(r.members(), [])
        if POSIX:
            self.assertEqual(r.ledger[0]["signal"], "SIGINT")
            self.assertEqual(r.returncode, -signal.SIGINT)  # it stopped on the cooperative signal

    def test_an_interrupt_ignoring_target_climbs_the_ladder(self):
        if not POSIX:
            self.skipTest("Windows has no cooperative signal to ignore: the job is terminated")
        code = "import signal, time\nsignal.signal(signal.SIGINT, signal.SIG_IGN)\nsignal.signal(signal.SIGTERM, " \
               "signal.SIG_IGN)\nend = time.time() + 120\nwhile time.time() < end: time.sleep(0.05)"
        r = self.range(code, grace_s=(0.3, 0.3))
        time.sleep(0.3)
        r.release()
        self.assertEqual([s["signal"] for s in r.ledger], ["SIGINT", "SIGTERM", "SIGKILL"])
        # the anchor dies with its group at SIGKILL, so the target's own status is not reported; the ledger says why
        self.assertIsNone(r.returncode)
        self.assertEqual(r.ledger[-1]["stage"], "kill")
        self.assertEqual(r.anchor_returncode, -signal.SIGKILL)

    def test_a_range_that_will_not_empty_is_residual_never_a_silent_success_and_blocks_by_default(self):
        r = self.range("import time; time.sleep(0.05)")
        r.wait(20)
        stuck = [Proc(4242, 1, None, None, "uninterruptible")]
        r._wait = 0.3  # a bounded wait, for the test
        with mock.patch.object(ProcessRange, "members", lambda self: stuck):
            t = time.monotonic()
            with self.assertRaisesRegex(RangeNotEmpty, r"^r: not empty after \['[a-z_]+'(, '[a-z_]+')*\]: "
                                                       r"\[\(4242, 'uninterruptible'\)\]$"):
                r.release()
            self.assertLess(time.monotonic() - t, 10)
        self.assertFalse(r._reaped)  # the anchor stays unreaped: the group id stays pinned
        blocked = ProcessRange("b", [PY, "-c", "import time; time.sleep(0.05)"], grace_s=(0.1, 0.1)).start()
        blocked.wait(20)
        state = {"members": stuck}
        with mock.patch.object(ProcessRange, "members", lambda self: state["members"]):
            th = threading.Thread(target=blocked.release, daemon=True)
            th.start()
            th.join(1.0)
            self.assertTrue(th.is_alive())  # unbounded by default: it blocks, it does not time out
            state["members"] = []
            th.join(10)
        self.assertFalse(th.is_alive())
        self.assertTrue(blocked._reaped)

    def test_an_escaped_child_is_detected_reported_and_never_signalled(self):
        if not POSIX:
            self.skipTest("a job without BREAKAWAY_OK has no way out; escaped() is empty there")
        pid_file = self.dir / "e.pid"
        escapee = f"import os, pathlib, time\nos.setsid()\npathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()))" \
                  "\ntime.sleep(2.5)"
        code = f"import subprocess, sys, time\nsubprocess.Popen([sys.executable, '-c', {escapee!r}])\ntime.sleep(1.0)"
        r = self.range(code)
        pid = read_pid(pid_file)
        time.sleep(0.2)
        self.assertEqual([p.pid for p in r.escaped()], [pid])
        self.assertNotIn(pid, [p.pid for p in r.members()])
        with self.assertRaisesRegex(pr.RangeEscaped, rf"^r: processes left the range and are alive: \[\({pid}, ['\"].+['\"]\)\]$"):
            r.release()
        self.assertTrue(alive(pid))  # reported, not signalled: it is not the range's
        self.assertTrue(gone(pid, 10))

    def test_D_024_red_before_a_writing_grandchild_outlives_a_cleanup_that_trusts_the_direct_child(self):
        wt, pid_file = self.dir / "worktree", self.dir / "w.pid"
        r = self.range(lingering(pid_file, 30, writes_into=wt))  # contained, so the test itself leaks nothing
        self.assertEqual(r.wait(20), 0)  # V1's order: the direct child exited, so clean up
        read_pid(pid_file)
        import shutil
        shutil.rmtree(wt, ignore_errors=True)
        time.sleep(0.4)
        self.assertTrue(wt.exists())  # RED: the grandchild is still writing into the removed worktree
        r.release()

    def test_D_024_green_after_the_range_is_proved_empty_before_the_worktree_is_removed(self):
        journal = _journal(self)
        wt, pid_file = self.dir / "worktree", self.dir / "w.pid"
        wt.mkdir()
        s = StoryScope("S1", emitter(journal))
        s.acquire(Directory("worktree", K.WORKTREE, wt))
        s.acquire(ProcessRange("range", [PY, "-c", lingering(pid_file, 30, writes_into=wt)], **FAST).start())
        writer = read_pid(pid_file)
        report = s.dispose()
        self.assertTrue(report.ok, report)
        self.assertFalse(alive(writer))
        time.sleep(0.4)
        self.assertFalse(wt.exists())  # GREEN: nothing is left to write into it
        self.assertEqual(released(journal), [("range", "RELEASED"), ("worktree", "RELEASED")])

    def test_PROC_OWN_1_a_controller_that_dies_leaves_no_owned_process_alive(self):
        pid_file, info = self.dir / "g.pid", self.dir / "info.json"
        controller = (f"import json, sys, time, pathlib\nsys.path.insert(0, {str(ROOT)!r})\n"
                      "from aisef2.runtime.process_range import ProcessRange\n"
                      f"r = ProcessRange('r', [sys.executable, '-c', {lingering(pid_file) + 'time.sleep(60)'!r}]).start()\n"
                      f"pathlib.Path({str(info)!r}).write_text(json.dumps([r.target_pid, r._anchor.pid]))\n"
                      "time.sleep(60)\n")
        c = subprocess.Popen([PY, "-P", "-c", controller])
        self.addCleanup(lambda: c.poll() is None and c.kill())
        grandchild = read_pid(pid_file)
        target, anchor = json.loads(_wait_text(info))
        for pid in (target, anchor, grandchild):
            self.assertTrue(alive(pid), pid)
        c.kill()  # SIGKILL / TerminateProcess: no disposer runs in the controller
        c.wait()
        for pid in (grandchild, target, anchor):
            self.assertTrue(gone(pid), f"{pid} survived its controller")

    def test_PROC_OWN_1_the_mutation_runner_timeout_takes_the_whole_tree_down(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("aisef_v2_mutation_p4", ROOT / "validation/v2/mutation.py")
        mutation = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mutation)
        pid_file = self.dir / "g.pid"
        (self.dir / "tests" / "hang").mkdir(parents=True)
        (self.dir / "tests" / "__init__.py").write_text("")
        (self.dir / "tests" / "hang" / "__init__.py").write_text("")
        (self.dir / "tests" / "hang" / "test_hang.py").write_text(
            "import unittest\nclass T(unittest.TestCase):\n    def test_hangs(self):\n"
            f"        exec({lingering(pid_file) + 'time.sleep(60)'!r})\n")
        with mock.patch.object(mutation, "TIMEOUT", 3):
            t = time.monotonic()
            self.assertEqual(mutation._run_tests(self.dir, ["tests/hang/test_hang.py"], mutation.ca.establish(self.dir)),
                             (False, 0))
        self.assertLess(time.monotonic() - t, 30)
        self.assertTrue(gone(read_pid(pid_file)), "the kill test's grandchild outlived the runner's timeout")

    def test_PROC_OWN_2_after_disposal_the_range_never_signals_again(self):
        r = self.range("import time; time.sleep(0.05)")
        r.wait(20)
        r.release()
        before = list(r.ledger)
        r.release()  # a second disposal is a no-op
        self.assertEqual(r.ledger, before)
        with self.assertRaisesRegex(pr.RangeError, "the anchor is reaped; the range is never signalled again"):
            r._signal("kill", signal.SIGTERM)
        self.assertEqual((r.members(), r.escaped()), ([], []))

    def test_start_failures_are_refused_and_leave_nothing_running(self):
        r = ProcessRange("missing", [str(self.dir / "no-such-program")], **FAST)
        with self.assertRaisesRegex(pr.RangeError, r"^missing: the target did not start \(SPAWN_FAILED "
                                                   r"[A-Za-z]+Error: .+\)$"):
            r.start()
        self.assertTrue(r._reaped)
        ok = self.range("import time; time.sleep(0.05)")
        with self.assertRaisesRegex(pr.RangeError, "r is already started"):
            ok.start()
        self.assertEqual(ProcessRange("never", [PY]).members(), [])
        self.assertEqual(ProcessRange("never", [PY]).escaped(), [])
        ProcessRange("never", [PY]).release()

    def test_the_anchor_runs_isolated_and_the_target_gets_exactly_the_given_environment(self):
        out = self.dir / "env.txt"
        env = {**os.environ, "AISEF_RANGE_ENV": "given"}
        self.assertNotIn("AISEF_RANGE_ENV", os.environ)
        r = self.range(f"import os, pathlib\npathlib.Path({str(out)!r}).write_text(os.environ.get('AISEF_RANGE_ENV', "
                       "'inherited'))", env=env)
        self.assertEqual(r._anchor.args, [PY, "-P", str(pr.ANCHOR)])  # -P: the anchor's directory never shadows stdlib
        self.assertEqual(r.wait(20), 0)
        self.assertEqual(out.read_text(), "given")
        self.assertTrue(r._pumper.daemon)

    def test_wait_says_none_at_once_when_the_anchor_is_gone_and_keeps_saying_it(self):
        r = self.range("import time\nend = time.time() + 120\nwhile time.time() < end: time.sleep(0.05)")
        self.assertIs(r.wait_empty(0.0), False)
        r._anchor.kill()  # the anchor dies without reporting the target's exit: its stdout closes
        for _ in range(2):
            t = time.monotonic()
            self.assertIsNone(r.wait(3.0))
            self.assertLess(time.monotonic() - t, 1.5)
        r.release()
        self.assertIs(r.wait_empty(0.0), True)

    @unittest.skipUnless(POSIX, "killpg is POSIX")
    def test_a_group_the_kernel_says_has_nobody_left_to_signal_is_measured_not_assumed(self):
        """macOS answers EPERM (not ESRCH) to killpg when every member is already exiting or a zombie (XNU killpg1
        with nfound == 0). Measured on 2026-09-23: two mutation runs died at once on it. The answer means nothing was
        there to signal; whether the range is empty is still measured, so a group that persists is a residual."""
        r = self.range("import time\nend = time.time() + 120\nwhile time.time() < end: time.sleep(0.05)")
        self.assertIsNone(r.wait(0.2))
        real, answered = os.killpg, []

        def eperm_once(group, sig):
            answered.append(sig)
            if len(answered) == 1:
                real(group, signal.SIGKILL)  # the members go away, as they were doing
                raise PermissionError(1, "Operation not permitted")
            return real(group, sig)
        with mock.patch.object(pr.os, "killpg", eperm_once):
            r.release()  # no exception: the group was measured empty after the answer
        self.assertEqual(r.members(), [])
        self.assertTrue(r._reaped)
        self.assertEqual([s["stage"] for s in r.ledger][:1], ["cooperative"])  # the attempt is still in the ledger
        stuck = ProcessRange("stuck", [PY, "-c", "import time; time.sleep(0.05)"], grace_s=(0.1, 0.1), wait_s=0.3).start()
        stuck.wait(20)
        with mock.patch.object(ProcessRange, "members", lambda self: [Proc(4243, 1, None, None, "persisting")]), \
                mock.patch.object(pr.os, "killpg", mock.Mock(side_effect=PermissionError(1, "denied"))), \
                self.assertRaises(RangeNotEmpty):
            stuck.release()  # a group that persists after that answer is a residual, never a silent success

    @unittest.skipUnless(POSIX, "the escape report reads the POSIX process table")
    def test_escapees_are_reported_in_pid_order(self):
        me = pr.process_table()
        lo, hi = sorted((os.getpid(), os.getppid()))
        r = self.range("pass")
        r.wait(20)
        with mock.patch.object(ProcessRange, "escaped", lambda self: [me[hi], me[lo]]), \
                self.assertRaises(pr.RangeEscaped) as e:
            r.release()
        self.assertEqual(str(e.exception), f"r: processes left the range and are alive: "
                                           f"{[(lo, me[lo].command), (hi, me[hi].command)]}")

    def test_a_controller_that_returns_without_disposing_exits_and_its_range_goes_with_it(self):
        info = self.dir / "info.json"
        long = "import time\nend = time.time() + 120\nwhile time.time() < end: time.sleep(0.05)"
        controller = (f"import json, sys, pathlib\nsys.path.insert(0, {str(ROOT)!r})\n"
                      "from aisef2.runtime.process_range import ProcessRange\n"
                      f"r = ProcessRange('r', [sys.executable, '-c', {long!r}]).start()\n"
                      f"pathlib.Path({str(info)!r}).write_text(json.dumps([r.target_pid, r._anchor.pid]))\n")
        c = subprocess.Popen([PY, "-P", "-c", controller])
        self.addCleanup(lambda: c.poll() is None and c.kill())
        self.assertEqual(c.wait(30), 0)  # no thread of the range holds the interpreter open
        for pid in json.loads(_wait_text(info)):
            self.assertTrue(gone(pid), f"{pid} outlived its controller")


class Backends(unittest.TestCase):
    def test_a_job_stop_is_recognised_only_with_its_stop_in_the_ledger(self):
        """Windows: TerminateJobObject gives every member JOB_EXIT_CODE; the adapter's reading of it is pure."""
        job = [{"stage": "terminate_job", "signal": "TerminateJobObject"}]
        self.assertIs(pr._Job.controller_stopped(pr.JOB_EXIT_CODE, job), True)
        for code, ledger in ((pr.JOB_EXIT_CODE, []), (pr.JOB_EXIT_CODE, [{"stage": "kill", "signal": "SIGKILL"}]),
                             (pr.JOB_EXIT_CODE + 1, job), (None, job)):
            with self.subTest(code=code, ledger=ledger):
                self.assertIs(pr._Job.controller_stopped(code, ledger), False)
        self.assertIs(pr._Posix.controller_stopped(-9, [{"stage": "kill", "signal": "SIGKILL"}]), False)
        self.assertIs(pr.BACKEND, pr._Posix if POSIX else pr._Job)


class Anchor(unittest.TestCase):
    def test_no_GO_no_target(self):
        """The anchor starts the target only after GO (the controller has made it a member of its job)."""
        kw = {"start_new_session": True} if POSIX else {}  # its watchdog kills its own group
        a = subprocess.Popen([PY, "-P", str(pr.ANCHOR)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             encoding="utf-8", **kw)
        out, _ = a.communicate(json.dumps({"argv": [PY, "-c", "pass"], "cwd": None, "env": None}) + "\nNOGO\n",
                               timeout=30)
        self.assertEqual(out, "")
        self.assertNotEqual(a.returncode, 0)

    @unittest.skipUnless(POSIX, "waitid (POSIX)")
    def test_the_reaper_reaps_every_child_but_the_target_and_keeps_doing_it(self):
        code = (f"import json, os, subprocess, sys, threading, time\nsys.path.insert(0, {str(ROOT)!r})\n"
                "from aisef2.runtime import range_anchor as ra\n"
                "def gone(pid, within=20):\n"                # WNOWAIT: watching never reaps it here
                "    end = time.monotonic() + within\n"
                "    while time.monotonic() < end:\n"
                "        try:\n"
                "            os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)\n"
                "        except ChildProcessError:\n            return True\n"
                "        time.sleep(0.02)\n"
                "    return False\n"
                "t = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(1.0); raise SystemExit(7)'])\n"
                "o = subprocess.Popen([sys.executable, '-c', 'pass'])\n"
                "threading.Thread(target=ra._reap_adopted, args=(t.pid, 0.01), daemon=True).start()\n"
                "first, status = gone(o.pid), t.wait()\n"    # the target's own wait reports its status
                "later = subprocess.Popen([sys.executable, '-c', 'pass'])\n"  # adopted after a moment with no child
                "print(json.dumps([first, status, gone(later.pid)]))\n")
        out = subprocess.run([PY, "-P", "-c", code], capture_output=True, encoding="utf-8", timeout=90)
        self.assertEqual(json.loads(out.stdout), [True, 7, True], out.stderr)

    def test_the_subreaper_is_asked_for_on_linux_only_and_its_absence_is_tolerated(self):
        from aisef2.runtime import range_anchor as ra
        for platform, lib, calls in (("linux", mock.Mock(), [mock.call(36, 1, 0, 0, 0)]), ("darwin", mock.Mock(), [])):
            with self.subTest(platform=platform), mock.patch.object(ra.sys, "platform", platform), \
                    mock.patch("ctypes.CDLL", return_value=lib) as cdll:
                ra._subreaper()
                self.assertEqual(lib.prctl.call_args_list, calls)
                self.assertEqual(cdll.call_count, len(calls))
        for error in (OSError("no libc"), AttributeError("no prctl")):
            with self.subTest(error=error), mock.patch.object(ra.sys, "platform", "linux"), \
                    mock.patch("ctypes.CDLL", side_effect=error):
                ra._subreaper()  # escaped orphans then re-parent to init: no crash


def _wait_text(path, within=20.0):
    deadline = time.monotonic() + within
    while not (path.exists() and path.read_text()):
        if time.monotonic() > deadline:
            raise AssertionError(f"{path} was never written")
        time.sleep(0.01)
    return path.read_text()


def _journal(test):
    j = Journal2()
    j._dir = tempfile.TemporaryDirectory(prefix="aisef2-p4-")
    test.addCleanup(j._dir.cleanup)
    j.dir = pathlib.Path(j._dir.name)
    j.path = j.dir / "journal.jsonl"
    j.clock = iter(float(n) for n in range(10 ** 6))
    j.addCleanup = test.addCleanup
    w = j.writer()
    j.story(w)
    return w


if __name__ == "__main__":
    unittest.main()
