"""WP-4.3 — RunScope, run lease, RunTerminationSentinel (RFC §18.1, §19; F8; P4-LIFETIME-SEMANTICS.md §4).

Kill set for `run_scope.py` and `sentinel.py`. RUN-1 (a durable run/end without CLEAN is TORN), RUN-2 (a held lease
blocks a second run whatever the journal says), RUN-3 (a writer that fails to close leaves OPEN), RUN-4 (a CLEAN that
cannot be recorded leaves OPEN); the lease is released last on every path; P3-RESIDUAL-DISPOSAL-ORDER.
"""

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import Enforcement, EventType as T  # noqa: E402
from aisef2.journal.format2 import ResourceKind as K, reconstruct  # noqa: E402
from aisef2.runtime import run_scope as rs, sentinel  # noqa: E402
from aisef2.runtime.capability import verified  # noqa: E402
from aisef2.runtime.run_scope import BEGIN_ORDER, SHUTDOWN_ORDER, LeaseHeld, RunScope, ShutdownRefused  # noqa: E402
from aisef2.runtime.runspec import resolve  # noqa: E402
from tests.v2.p4.world import SHA, Fake, closed_after  # noqa: E402

CLEAN_SHUTDOWN = [*BEGIN_ORDER, *SHUTDOWN_ORDER]


def spec():
    return resolve([verified("kernel", b"aisef2 kernel", Enforcement.FULL)], {"retries": {"value": 2, "layer": "project"}},
                   SHA)


def plan(run):
    """The frozen plan the admissions below name (the qualification_counters projection refuses any other)."""
    if not any(e.type == T.PLAN_FROZEN.value for e in run.events):
        run.append(T.PLAN_FROZEN, {"plan_id": "PLAN-P4", "plan_hash": "b" * 64, "roles": {"C1": "INTRODUCE"}})


def end_story(run, story="S1", resources=()):
    plan(run)
    run.append(T.STORY_BEGIN, {"story_id": story, "parent": SHA})
    scope = run.story(story)
    for r in resources:
        scope.acquire(r)
    run.append(T.STORY_ADMITTED, {"story_id": story, "parent": SHA, "admitted": True, "developer_call_permitted": True,
                                  "dispositions": {"C1": "READY"}})
    run.append(T.STORY_COMMIT, {"story_id": story, "revision": SHA})
    run.append(T.STORY_DISPOSE, {"story_id": story})
    scope.dispose()
    run.append(T.STORY_END, {"story_id": story})


class Lifetime(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory(prefix="aisef2-run-")
        self.addCleanup(self._d.cleanup)
        self.root = pathlib.Path(self._d.name)

    def run_scope(self, run_id="run-1", **kw):
        return closed_after(self, RunScope(self.root, run_id, spec=kw.pop("spec", spec), clock=lambda: 1.0, **kw))

    def journal(self, r):
        return reconstruct(r.journal_path.read_bytes().decode("utf-8"))

    def test_a_clean_run_follows_the_normative_order_and_releases_the_lease_last(self):
        r = self.run_scope()
        self.assertEqual(r.begin(), sentinel.Preflight(sentinel.NONE, None, None))
        end_story(r, resources=[Fake("wt", K.WORKTREE)])
        r.shutdown()
        self.assertEqual(r.trace, CLEAN_SHUTDOWN)
        self.assertFalse(r.lease.held)
        self.assertEqual(sentinel.read(r.sentinel_path)["state"], "CLEAN")
        types = [e.type for e in self.journal(r).events]
        self.assertEqual(types[:3], ["run/begin", "capability/resolved", "run/spec-resolved"])
        self.assertEqual(types[-2:], ["run/dispose-begin", "run/end"])
        second = self.run_scope("run-2")
        pre = second.begin()
        self.assertEqual((pre.previous, pre.run_id, pre.residuals), ("CLEAN", "run-1", ()))
        self.assertEqual(pre.journal, str(r.journal_path))

    def test_story_scopes_dispose_before_run_level_finalisation(self):
        r = self.run_scope()
        r.begin()
        log = []
        plan(r)
        r.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})
        r.story("S1").acquire(Fake("session", K.SESSION, log))
        r.append(T.STORY_ADMITTED, {"story_id": "S1", "parent": SHA, "admitted": True,
                                    "developer_call_permitted": True, "dispositions": {"C1": "READY"}})
        r.append(T.STORY_COMMIT, {"story_id": "S1", "revision": SHA})
        r.append(T.STORY_DISPOSE, {"story_id": "S1"})
        r.append(T.STORY_END, {"story_id": "S1"})   # the transaction ended; its scope is still holding
        reports = r.shutdown()
        self.assertEqual((log, [x.ok for x in reports]), (["session"], [True]))
        types = [e.type for e in self.journal(r).events]
        self.assertLess(types.index("story/resource-released"), types.index("run/dispose-begin"))
        self.assertIs(r.story("S1"), r.story("S1"))  # a new scope only for a new attempt

    def test_P3_RESIDUAL_DISPOSAL_ORDER_a_successful_shutdown_is_refused_while_a_story_is_open(self):
        r = self.run_scope()
        r.begin()
        plan(r)
        r.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})
        before = r.events
        with self.assertRaisesRegex(ShutdownRefused, r"stories \['S1'\] are not ENDED: .* interrupt the run instead"):
            r.shutdown()
        self.assertEqual((r.events, r.lease.held, r.trace[-1]), (before, True, "execution"))
        r.append(T.STORY_ADMITTED, {"story_id": "S1", "parent": SHA, "admitted": True,
                                    "developer_call_permitted": True, "dispositions": {"C1": "READY"}})
        r.append(T.STORY_COMMIT, {"story_id": "S1", "revision": SHA})
        r.append(T.STORY_DISPOSE, {"story_id": "S1"})
        r.append(T.STORY_END, {"story_id": "S1"})
        r.shutdown()
        self.assertEqual(r.trace, CLEAN_SHUTDOWN)
        with self.assertRaisesRegex(ShutdownRefused, "run run-1 is ENDED"):
            r.shutdown()
        with self.assertRaisesRegex(Exception, "run run-1 is ENDED: nothing more is appended"):
            r.append(T.RUN_END, {})

    def test_RUN_1_a_process_killed_after_a_durable_run_end_and_before_CLEAN_is_torn(self):
        script = (f"import os, signal, sys\nsys.path.insert(0, {str(ROOT)!r})\n"
                  "from unittest import mock\nfrom tests.v2.p4.test_run_scope import RunScope, end_story, spec\n"
                  "from aisef2.runtime import sentinel\n"
                  f"r = RunScope({str(self.root)!r}, 'run-1', spec=spec, clock=lambda: 1.0)\n"
                  "r.begin()\nend_story(r)\n"
                  "die = lambda *a: os.kill(os.getpid(), getattr(signal, 'SIGKILL', signal.SIGTERM))\n"
                  "with mock.patch.object(sentinel, 'mark_clean', die):\n    r.shutdown()\n")
        done = subprocess.run([sys.executable, "-P", "-c", script], capture_output=True, encoding="utf-8")
        self.assertNotEqual(done.returncode, 0, done.stderr)
        j = reconstruct((self.root / "journals" / "run-1.jsonl").read_bytes().decode("utf-8"))
        self.assertEqual(j.events[-1].type, "run/end")  # the journal is complete and authoritative ...
        nxt = self.run_scope("run-2")
        pre = nxt.begin()  # ... the lease died with its process ...
        self.assertEqual((pre.previous, pre.run_id, pre.residuals), ("TORN", "run-1", ()))  # ... and the run is TORN

    def test_RUN_2_a_held_lease_blocks_a_second_run_even_with_run_end_written(self):
        first = self.run_scope("run-1")
        first.begin()
        end_story(first)
        second = self.run_scope("run-2")
        attempts, real_clean = [], sentinel.mark_clean

        def clean_later(path, run_id):  # run/end is durable and the writer closed; CLEAN not yet written
            try:
                second.begin()
            except LeaseHeld as e:
                attempts.append(str(e))
            real_clean(path, run_id)
        with mock.patch.object(sentinel, "mark_clean", clean_later):
            first.shutdown()
        self.assertEqual(len(attempts), 1)
        self.assertIn("is held by another run", attempts[0])
        self.assertEqual(second.trace, [])  # it read nothing and wrote nothing
        self.assertEqual(second.begin().previous, "CLEAN")
        holder = subprocess.Popen([sys.executable, "-P", "-c", (
            f"import sys, time\nsys.path.insert(0, {str(ROOT)!r})\nfrom aisef2.runtime.run_scope import RunLease\n"
            f"l = RunLease({str(self.root / 'other.lease')!r})\nl.acquire()\nprint('held', flush=True)\n"
            "time.sleep(30)\n")], stdout=subprocess.PIPE, encoding="utf-8")
        self.addCleanup(lambda: holder.poll() is None and holder.kill())
        self.assertEqual(holder.stdout.readline().strip(), "held")
        lease = rs.RunLease(self.root / "other.lease")
        with self.assertRaises(LeaseHeld):
            lease.acquire()
        holder.kill()
        holder.wait()
        holder.stdout.close()
        lease.acquire()  # released by the OS with the process that held it
        lease.release()
        lease.release()

    def test_RUN_3_a_writer_that_fails_to_close_leaves_the_sentinel_open_and_the_lease_still_released_last(self):
        r = self.run_scope()
        r.begin()
        end_story(r)
        with mock.patch.object(r._writer, "close", side_effect=OSError("EIO on close")), \
                self.assertRaisesRegex(OSError, "EIO on close"):
            r.shutdown()
        self.assertEqual(r.trace, [*BEGIN_ORDER, *SHUTDOWN_ORDER[:3], "lease released"])
        self.assertEqual(sentinel.read(r.sentinel_path)["state"], "OPEN")
        self.assertFalse(r.lease.held)
        self.assertEqual(self.run_scope("run-2").begin().previous, "TORN")

    def test_RUN_4_a_clean_that_cannot_be_recorded_leaves_the_sentinel_open(self):
        for fault in ("fsync", "replace"):
            with self.subTest(fault=fault):
                r = self.run_scope(f"run-{fault}")
                r.begin()
                end_story(r)
                real_clean = sentinel.mark_clean

                def failing(path, run_id, fault=fault, real_clean=real_clean):  # the CLEAN write only, not the journal
                    with mock.patch.object(sentinel.os, fault, side_effect=OSError(f"{fault} failed")):
                        real_clean(path, run_id)
                with mock.patch.object(sentinel, "mark_clean", failing), \
                        self.assertRaisesRegex(OSError, f"{fault} failed"):
                    r.shutdown()
                self.assertEqual(r.trace, [*BEGIN_ORDER, *SHUTDOWN_ORDER[:4], "lease released"])
                self.assertEqual(sentinel.read(r.sentinel_path), {"state": "OPEN", "run_id": f"run-{fault}",
                                                                  "journal": str(r.journal_path)})
                self.assertFalse(r.lease.held)
                self.assertEqual(sentinel.preflight(r.sentinel_path).previous, "TORN")

    def test_the_lease_is_held_before_any_state_read_and_a_failed_begin_still_releases_it_last(self):
        r = self.run_scope()
        seen = []
        real = sentinel.preflight
        with mock.patch.object(sentinel, "preflight", lambda p: seen.append(r.lease.held) or real(p)):
            r.begin()
        self.assertEqual(seen, [True])
        r.lease.release()
        bad = self.run_scope("run-bad", spec=lambda: (_ for _ in ()).throw(RuntimeError("no RunSpec")))
        with self.assertRaisesRegex(RuntimeError, "no RunSpec"):
            bad.begin()
        self.assertEqual(bad.trace, ["lease", "sentinel OPEN", "journal writer", "lease released"])
        self.assertFalse(bad.lease.held)
        self.assertEqual(sentinel.read(bad.sentinel_path)["state"], "OPEN")  # conservative: the next run sees TORN
        with self.assertRaisesRegex(Exception, "^run run-bad is FAILED: a RunScope begins once$"):
            bad.begin()
        early = self.run_scope("run-early")
        with mock.patch.object(sentinel, "mark_open", side_effect=OSError("read-only")), \
                self.assertRaisesRegex(OSError, "read-only"):
            early.begin()
        self.assertEqual(early.trace, ["lease", "lease released"])

    def test_the_preflight_names_the_previous_runs_residuals(self):
        r = self.run_scope()
        r.begin()
        r.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})
        r.story("S1").acquire(Fake("wt", K.WORKTREE))
        r.append(T.TOOL_INVOKED, {"story_id": "S1", "call_id": "c1", "tool": "pytest"})
        r._writer.close()
        r.lease.release()  # as if the process died here
        pre = self.run_scope("run-2").begin()
        self.assertEqual(pre.previous, "TORN")
        self.assertEqual(pre.residuals, ("S1: WORKTREE wt acquired at seq 4, never released",
                                         "S1: tool call c1 (pytest) has no result"))
        missing = self.root / "gone.sentinel"
        sentinel.mark_open(missing, "run-x", self.root / "no-journal.jsonl")
        self.assertEqual(sentinel.preflight(missing).residuals,
                         (f"the journal {str(self.root / 'no-journal.jsonl')!r} is missing",))

    def test_a_sentinel_marks_clean_only_its_own_open_run(self):
        p = self.root / "s"
        with self.assertRaisesRegex(sentinel.SentinelError, "^" + re.escape(f"{p} is not the OPEN sentinel of run "
                                                                            "r1: None") + "$"):
            sentinel.mark_clean(p, "r1")
        sentinel.mark_open(p, "r1", "j")
        self.assertEqual(p.read_bytes(), b'{"journal": "j", "run_id": "r1", "state": "OPEN"}\n')
        with self.assertRaisesRegex(sentinel.SentinelError, "is not the OPEN sentinel of run r2"):
            sentinel.mark_clean(p, "r2")
        sentinel.mark_clean(p, "r1")
        self.assertEqual(json.loads(p.read_text()), {"state": "CLEAN", "run_id": "r1", "journal": "j"})
        with self.assertRaisesRegex(sentinel.SentinelError, "is not the OPEN sentinel"):
            sentinel.mark_clean(p, "r1")
        p.write_text("not json")
        self.assertEqual(sentinel.read(p), {"state": "UNREADABLE"})
        self.assertEqual(sentinel.preflight(p).previous, "TORN")
        p.write_text("[1]")
        self.assertEqual(sentinel.read(p), {"state": "UNREADABLE"})
        (self.root / "dir.sentinel").mkdir()
        self.assertEqual(sentinel.read(self.root / "dir.sentinel"), {"state": "UNREADABLE"})  # it cannot be read
        self.assertFalse((self.root / "s.tmp").exists())
        with mock.patch.object(sentinel.os, "write", lambda fd, b: 1), \
                self.assertRaisesRegex(sentinel.SentinelError, "short write"):
            sentinel.mark_open(p, "r3", "j")
        if os.name == "posix":
            with mock.patch.object(sentinel.os, "fsync", wraps=os.fsync) as fsync:
                sentinel.mark_open(p, "r4", "j")
            self.assertEqual(fsync.call_count, 2)  # the file and its directory

    def test_files_are_opened_binary(self):
        """Windows' CRT opens low-level files in text mode (LF -> CRLF) unless O_BINARY is set."""
        opened, real, native = [], os.open, hasattr(os, "O_BINARY")

        def spy(path, flags, mode=0o777):
            opened.append((pathlib.Path(path).name, flags))
            return real(path, flags if native else flags & ~0x8000, mode)  # on Windows the flag is real, and needed
        with mock.patch.object(os, "O_BINARY", 0x8000, create=True), mock.patch.object(os, "open", spy):
            sentinel.mark_open(self.root / "s", "r1", "j")
            lease = rs.RunLease(self.root / "l")
            lease.acquire()
            lease.release()
        flags = dict(opened)
        self.assertTrue(flags["s.tmp"] & 0x8000 and flags["s.tmp"] & os.O_TRUNC and flags["s.tmp"] & os.O_CREAT)
        self.assertTrue(flags["l"] & 0x8000 and flags["l"] & os.O_CREAT)

    def test_a_run_root_is_made_with_its_parents_and_a_story_keeps_its_scope_until_disposed(self):
        r = closed_after(self, RunScope(self.root / "a" / "b", "run-n", spec=spec, clock=lambda: 1.0))
        r.begin()
        self.assertTrue(r.journal_path.exists())
        with self.assertRaisesRegex(Exception, "^run run-n is RUNNING: a RunScope begins once$"):
            r.begin()
        plan(r)
        for story in ("S3", "S1", "S2"):
            r.append(T.STORY_BEGIN, {"story_id": story, "parent": SHA})
        self.assertEqual(r.open_stories(), ["S1", "S2", "S3"])
        first = r.story("S1")
        self.assertIs(r.story("S1"), first)
        first.dispose()
        second = r.story("S1")
        self.assertIsNot(second, first)
        self.assertEqual(second.state, "ACTIVE")

    def test_residuals_of_a_journal_that_cannot_be_read_are_named(self):
        self.assertEqual(sentinel.residuals("garbage\n"), ("the journal cannot be reconstructed: line 0 is not JSON",))
        self.assertEqual(sentinel.residuals(""), ())
        from aisef2.journal.writer import JournalWriter
        one = JournalWriter(self.root / "one.jsonl", clock=lambda: 0.0)
        one.append(T.RUN_BEGIN, {"journal_format": 1, "run_id": "r"})
        one.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})
        one.append(T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": ["C1"]})
        one.close()  # format 1 has no provider/result: its requests are never residuals
        self.assertEqual(sentinel.residuals((self.root / "one.jsonl").read_text(encoding="utf-8")), ())
        r = self.run_scope()
        r.begin()
        plan(r)
        r.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})
        r.append(T.STORY_ADMITTED, {"story_id": "S1", "parent": SHA, "admitted": True,
                                    "developer_call_permitted": True, "dispositions": {"C1": "READY"}})
        req = r.append(T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": ["C1"]})
        inv = r.append(T.TOOL_INVOKED, {"story_id": "S1", "call_id": "c1", "tool": "pytest"})
        r.append(T.TOOL_RESULT, {"story_id": "S1", "call_id": "c1", "outcome": "COMPLETED", "signal": 0,
                                 "provenance": "NONE", "synthetic": False, "detail": ""}, source_seqs=(inv.seq,))
        scope = r.story("S1")
        scope.acquire(Fake("s", K.SESSION, fail="gone"))
        scope.dispose()
        text = r.journal_path.read_bytes().decode("utf-8")
        self.assertEqual(sentinel.residuals(text + '{"torn'), (
            f"torn tail after seq {len(r.events) - 1}", "S1: SESSION s FAILED: OSError: gone",
            f"S1: provider/request at seq {req.seq} has no result"))


if __name__ == "__main__":
    unittest.main()
