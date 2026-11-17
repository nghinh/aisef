"""WP-4.6 — interruption, provenance and deterministic disposal (RFC §17.1, §20.2; P4-LIFETIME-SEMANTICS.md §7).

Kill set for `tool.py`, `repair.py` and `RunScope.interrupt`. INTERRUPT-SIG-1 (a controller-issued stop is told apart
from the subject's own signal exit), INTERRUPT-SIG-2 (a signal exit never becomes an owner, ENVIRONMENT included),
INTERRUPT-SIG-3 (unknown after dispatch is OUTCOME_UNKNOWN; before dispatch NOT_STARTED); no interruption creates a gap;
repair is idempotent and byte-identical; abandonment is explicit; scopes dispose before the run finishes; disposal
failures stay evidence. Real SIGINT and SIGKILL mid-story on POSIX.
"""

import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import EventType as T  # noqa: E402
from aisef2.journal.event import JournalError  # noqa: E402
from aisef2.journal import format3 as f3  # noqa: E402
from aisef2.journal.format2 import ResourceKind as K  # noqa: E402
from aisef2.journal.format3 import reconstruct  # noqa: E402 — every format, each read as written
from aisef2.runtime import repair as rp, sentinel  # noqa: E402
from aisef2.runtime.process_range import BACKEND, JOB_EXIT_CODE, _Job, _Posix  # noqa: E402
from aisef2.runtime.run_scope import RunScope  # noqa: E402
from aisef2.runtime.tool import ToolCall, outcome  # noqa: E402
from tests.v2.p4.test_run_scope import plan, spec  # noqa: E402
from tests.v2.p4.world import SHA, Fake, closed_after  # noqa: E402

PY = sys.executable
POSIX = os.name == "posix"
FAST = {"grace_s": (1.0, 1.0), "wait_s": 10.0}
LONG = "import time\nend = time.time() + 120\nwhile time.time() < end: time.sleep(0.05)"  # bounded: a leak ends


def kinds(run):
    return [e.type for e in run.events]


class Interruption(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory(prefix="aisef2-int-")
        self.addCleanup(self._d.cleanup)
        self.root = pathlib.Path(self._d.name)
        self.run = closed_after(self, RunScope(self.root, "run-i", spec=spec, clock=lambda: 1.0))
        self.run.begin()
        plan(self.run)
        self.run.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})

    def tool(self, call="c1", code=LONG):
        return ToolCall(self.run, "S1", call, "python", [PY, "-c", code], **FAST)

    def result(self):
        return next(e for e in reversed(self.run.events) if e.type == T.TOOL_RESULT.value).data

    def test_a_tool_that_finishes_is_measured_and_its_range_released(self):
        for n, (code, want) in enumerate((("pass", ("COMPLETED", 0, "NONE")), ("raise SystemExit(3)", ("FAILED", 0, "NONE")))):
            with self.subTest(code=code):
                call = self.tool(f"c{n}", code)
                call.dispatch()
                call.finish(20)
                r = self.result()
                self.assertEqual((r["outcome"], r["signal"], r["provenance"], r["synthetic"]), want + (False,))
        self.assertEqual(r["detail"], "exit status 3")
        released = [e.data["status"] for e in self.run.events if e.type == T.STORY_RESOURCE_RELEASED.value]
        self.assertEqual(released, ["RELEASED", "RELEASED"])
        self.assertNotIn(T.FAILURE_OBSERVED.value, kinds(self.run))

    def test_INTERRUPT_SIG_1_a_controller_stop_is_attributed_to_the_controller(self):
        call = self.tool()
        call.dispatch()
        call.finish(0.3)  # still running: the controller stops it
        r = self.result()
        self.assertEqual((r["outcome"], r["provenance"]), ("SIGNALLED", "CONTROLLER"))
        self.assertIn("by the controller", r["detail"])
        self.assertTrue(call.range.ledger)

    def test_INTERRUPT_SIG_2_a_subject_signal_exit_never_becomes_an_owner(self):
        call = self.tool(code="import os, signal\nos.kill(os.getpid(), signal.SIGTERM)")
        call.dispatch()
        call.finish(20)
        r = self.result()
        if POSIX:
            self.assertEqual((r["outcome"], r["signal"], r["provenance"]), ("SIGNALLED", signal.SIGTERM, "UNKNOWN"))
            self.assertIn("not sent by the controller", r["detail"])
        else:  # Windows turns os.kill into TerminateProcess(15): an exit status, measured as such
            self.assertEqual((r["outcome"], r["provenance"]), ("FAILED", "NONE"))
        self.assertNotIn(T.FAILURE_OBSERVED.value, kinds(self.run))  # no owner, ENVIRONMENT least of all
        self.assertEqual(call.range.ledger, [])

    def test_the_outcome_table(self):
        term = [{"stage": "terminate", "signal": "SIGTERM"}]  # a signal every platform names
        sig = int(signal.SIGTERM)
        none = {"signal": 0, "provenance": "NONE"}
        self.assertEqual(outcome(0, 0, []), {"outcome": "COMPLETED", **none, "detail": ""})
        self.assertEqual(outcome(2, 0, []), {"outcome": "FAILED", **none, "detail": "exit status 2"})
        self.assertEqual(outcome(None, None, []), {"outcome": "FAILED", **none, "detail": "exit status not reported"})
        self.assertEqual(outcome(-sig, 0, term), {
            "outcome": "SIGNALLED", "signal": sig, "provenance": "CONTROLLER",
            "detail": "the tool died by a signal: SIGTERM, sent by the controller"})
        self.assertEqual(outcome(-sig, 0, []), {
            "outcome": "SIGNALLED", "signal": sig, "provenance": "UNKNOWN",
            "detail": "the tool died by a signal: SIGTERM, not sent by the controller"})
        self.assertEqual(outcome(None, -sig, term), {
            "outcome": "SIGNALLED", "signal": sig, "provenance": "CONTROLLER",
            "detail": "the range died by a signal before the tool's status was reported: SIGTERM, sent by the "
                      "controller"})
        self.assertEqual(outcome(None, -sig, [])["provenance"], "UNKNOWN")
        self.assertEqual(outcome(None, 0, term)["outcome"], "FAILED")  # the anchor exited: no signal to name
        self.assertEqual(outcome(-99, 0, [])["detail"], "the tool died by a signal: signal 99, not sent by the controller")

    def test_a_job_stop_is_the_controllers_only_with_its_stop_in_the_ledger(self):
        """Windows: TerminateJobObject gives every member JOB_EXIT_CODE; the job adapter alone reads it (pure)."""
        job = [{"stage": "terminate_job", "signal": "TerminateJobObject"}]
        stopped = {"outcome": "SIGNALLED", "signal": 9, "provenance": "CONTROLLER",
                   "detail": "terminated with its job by the controller (TerminateJobObject)"}
        self.assertEqual(outcome(JOB_EXIT_CODE, None, job, _Job), stopped)
        self.assertEqual(outcome(JOB_EXIT_CODE, None, [], _Job)["outcome"], "FAILED")  # a tool's own exit status
        self.assertEqual(outcome(JOB_EXIT_CODE, None, [{"stage": "terminate", "signal": "SIGTERM"}], _Job)["outcome"],
                         "FAILED")
        self.assertEqual(outcome(JOB_EXIT_CODE + 1, None, job, _Job)["outcome"], "FAILED")
        self.assertEqual(outcome(JOB_EXIT_CODE, None, job, _Posix)["outcome"], "FAILED")  # POSIX: only signal exits
        self.assertEqual(outcome(None, JOB_EXIT_CODE, job, _Job), stopped)  # the anchor went with the job it reported
        self.assertEqual(outcome(None, JOB_EXIT_CODE, [], _Job)["outcome"], "FAILED")
        self.assertIs(BACKEND, _Posix if POSIX else _Job)

    def test_a_call_is_dispatched_and_finished_once_and_returns_what_it_wrote(self):
        call = self.tool("c1", "pass")
        with self.assertRaisesRegex(RuntimeError, "^call c1 is PENDING$"):
            call.finish()
        invoked = call.dispatch()
        self.assertEqual((invoked, invoked.type), (self.run.events[-1], "tool/invoked"))
        with self.assertRaisesRegex(RuntimeError, "^call c1 is DISPATCHED$"):
            call.dispatch()
        recorded = call.finish(20)
        self.assertEqual((recorded.type, recorded.data["outcome"], recorded.source_seqs),
                         ("tool/result", "COMPLETED", (invoked.seq,)))
        self.assertIs(recorded, call.recorded)
        with self.assertRaisesRegex(RuntimeError, "^call c1 is DONE$"):
            call.finish()
        self.assertIsNone(call.close())

    def test_the_closers_of_a_call_say_what_is_known(self):
        pending, running = self.tool("p"), self.tool("r")
        running.dispatch()
        base = {"story_id": "S1", "signal": 0, "provenance": "NONE", "synthetic": True}
        self.assertEqual(dict(pending.close().data), {**base, "call_id": "p", "outcome": "NOT_STARTED",
                                                      "detail": "interrupted before dispatch"})
        self.assertEqual(dict(running.close().data), {**base, "call_id": "r", "outcome": "OUTCOME_UNKNOWN",
                                                      "detail": "interrupted after dispatch: what the tool did is not "
                                                                "known"})
        self.assertEqual((pending.state, running.state), ("CLOSED", "CLOSED"))
        self.assertIsNone(running.close())
        reports = self.run.interrupt()  # disposes the scope: the running tool's range is released
        self.assertEqual([(r.story_id, [x.resource for x in r.records]) for r in reports], [("S1", ["tool r"])])
        self.assertFalse(running.range.members())

    def test_INTERRUPT_SIG_3_closers_distinguish_not_started_from_outcome_unknown_and_leave_no_gap(self):
        running, done = self.tool("run"), self.tool("done", "pass")
        self.tool("wait")  # registered with the run, never dispatched
        done.dispatch()
        done.finish(20)
        running.dispatch()
        self.run.append(T.STORY_ADMITTED, {"story_id": "S1", "parent": SHA, "admitted": True,
                                           "developer_call_permitted": True, "dispositions": {"C1": "READY"}})
        req = self.run.append(T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": ["C1"], "budget_owner": "DEVELOPER"})
        target = running.range.target_pid
        self.run.interrupt()
        results = {e.data["call_id"]: e for e in self.run.events if e.type == T.TOOL_RESULT.value}
        self.assertEqual((results["run"].data["outcome"], results["run"].source_seqs),
                         ("OUTCOME_UNKNOWN", (running._invoked.seq,)))
        self.assertEqual((results["wait"].data["outcome"], results["wait"].source_seqs), ("NOT_STARTED", ()))
        self.assertTrue(all(results[c].data["synthetic"] for c in ("run", "wait")))
        self.assertFalse(results["done"].data["synthetic"])  # a closer is never mistaken for a measurement
        provider = next(e for e in self.run.events if e.type == T.PROVIDER_RESULT.value)
        self.assertEqual((provider.data["outcome"], provider.data["synthetic"], provider.source_seqs),
                         ("OUTCOME_UNKNOWN", True, (req.seq,)))
        self.assertEqual(provider.data["detail"], "interrupted before its result")
        interrupted = next(e for e in self.run.events if e.type == T.RUN_INTERRUPTED.value)
        self.assertEqual({results[c].time for c in ("run", "wait")} | {provider.time}, {interrupted.time})
        self.assertIsNone(running.close())
        j = reconstruct(self.run.journal_path.read_bytes().decode("utf-8"))  # seq == index: no gap
        self.assertEqual([e.seq for e in j.events], list(range(len(j.events))))
        self.assertEqual(kinds(self.run)[-2:], ["run/dispose-begin", "run/end"])
        self.assertFalse(running.range.members())
        self.assertNotIn(target, [p.pid for p in running.range.members()])

    def test_an_interrupted_run_disposes_its_scopes_before_it_finishes_and_stays_torn(self):
        log = []
        self.run.story("S1").acquire(Fake("wt", K.WORKTREE, log))
        self.run.story("S1").acquire(Fake("session", K.SESSION, log, fail="already closed"))
        self.run.interrupt()
        self.assertEqual(self.run.trace[-6:], ["interrupted", "operations closed", "story scopes disposed", "run/end",
                                               "journal writer closed", "lease released"])
        self.assertEqual(log, ["session", "wt"])
        released = [(e.data["resource"], e.data["status"], e.data["synthetic"]) for e in self.run.events
                    if e.type == T.STORY_RESOURCE_RELEASED.value]
        self.assertEqual(released, [("session", "FAILED", False), ("wt", "RELEASED", False)])  # still evidence
        self.assertLess(kinds(self.run).index("story/resource-released"), kinds(self.run).index("run/dispose-begin"))
        self.assertEqual(sentinel.read(self.run.sentinel_path)["state"], "OPEN")
        nxt = closed_after(self, RunScope(self.root, "run-2", spec=spec))
        pre = nxt.begin()
        self.assertEqual(pre.previous, "TORN")
        self.assertEqual(pre.residuals, ("S1: SESSION session FAILED: OSError: already closed",))
        with self.assertRaisesRegex(Exception, "^run run-i is ENDED: it cannot be interrupted$"):
            self.run.interrupt()

    def test_a_second_interrupt_during_disposal_abandons_and_says_so(self):
        log = []
        self.run.story("S1").acquire(Fake("scratch", K.SCRATCH, log))
        self.run.story("S1").acquire(Fake("wt", K.WORKTREE, log))

        class SecondInterrupt(Fake):
            def release(inner):
                super().release()
                signal.raise_signal(signal.SIGINT)  # a real SIGINT, delivered to the handler disposal installed
        self.run.story("S1").acquire(SecondInterrupt("session", K.SESSION, log))
        before = signal.getsignal(signal.SIGINT)
        self.run.interrupt()
        self.assertIs(signal.getsignal(signal.SIGINT), before)  # the handler is restored
        self.assertEqual(log, ["session"])
        released = [(e.data["resource"], e.data["status"]) for e in self.run.events
                    if e.type == T.STORY_RESOURCE_RELEASED.value]
        self.assertEqual(released, [("session", "RELEASED"), ("wt", "RESIDUAL"), ("scratch", "RESIDUAL")])
        last = self.run.events[-1]
        self.assertEqual((last.type, dict(last.data)), ("run/interrupted", {"abandoned": True}))
        self.assertNotIn("run/end", kinds(self.run))
        self.assertIn("abandoned", self.run.trace)
        self.assertFalse(self.run.lease.held)

    def test_an_interrupt_during_disposal_only_asks_for_abandonment(self):
        log, answers = [], []

        class Reentrant(Fake):
            def release(inner):
                super().release()
                answers.append(self.run.interrupt())  # the second interrupt, however it arrives
        self.run.story("S1").acquire(Fake("wt", K.WORKTREE, log))
        self.run.story("S1").acquire(Reentrant("session", K.SESSION, log))
        self.run.interrupt()
        self.assertEqual((answers, log), ([[]], ["session"]))
        self.assertEqual(dict(self.run.events[-1].data), {"abandoned": True})

    def test_interruptible_turns_a_keyboard_interrupt_into_an_interruption(self):
        with self.run.interruptible():
            raise KeyboardInterrupt
        self.assertEqual(kinds(self.run)[-1], "run/end")
        self.assertIn("interrupted", self.run.trace)


class Repair(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory(prefix="aisef2-repair-")
        self.addCleanup(self._d.cleanup)
        self.root = pathlib.Path(self._d.name)

    def died(self, interrupted=False, stories=()):
        """A run whose process died mid-story: a finished tool, a dispatched one, an open request, held resources."""
        run = closed_after(self, RunScope(self.root, "run-r", spec=spec,
                                          clock=iter(float(n) for n in range(100)).__next__))
        run.begin()
        plan(run)
        run.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})
        run.story("S1").acquire(Fake("wt", K.WORKTREE))
        run.story("S1").acquire(Fake("session", K.SESSION))
        for story in stories:
            run.append(T.STORY_BEGIN, {"story_id": story, "parent": SHA})
            run.story(story).acquire(Fake(f"wt-{story}", K.WORKTREE))
        done = run.append(T.TOOL_INVOKED, {"story_id": "S1", "call_id": "c0", "tool": "ruff"})
        run.append(T.TOOL_RESULT, {"story_id": "S1", "call_id": "c0", "outcome": "COMPLETED", "signal": 0,
                                   "provenance": "NONE", "synthetic": False, "detail": ""}, source_seqs=(done.seq,))
        run.append(T.STORY_ADMITTED, {"story_id": "S1", "parent": SHA, "admitted": True,
                                      "developer_call_permitted": True, "dispositions": {"C1": "READY"}})
        run.append(T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": ["C1"], "budget_owner": "DEVELOPER"})
        run.append(T.TOOL_INVOKED, {"story_id": "S1", "call_id": "c1", "tool": "pytest"})
        if interrupted:
            run.append(T.RUN_INTERRUPTED, {"abandoned": False})
        run._writer.close()
        run.lease.release()
        return run, run.journal_path.read_bytes().decode("utf-8")

    def test_repair_closes_everything_open_synthetically_at_the_last_real_time(self):
        run, text = self.died()
        fixed = rp.repair(text + '{"chain":"trun')
        self.assertTrue(fixed.startswith(text))
        j = reconstruct(fixed)
        added = j.events[len(run.events):]
        self.assertEqual([(e.type, e.data.get("outcome", e.data.get("status"))) for e in added], [
            ("tool/result", "OUTCOME_UNKNOWN"), ("provider/result", "OUTCOME_UNKNOWN"),
            ("story/resource-released", "RESIDUAL"), ("story/resource-released", "RESIDUAL"),
            ("run/interrupted", None), ("run/end", None)])
        self.assertEqual([e.data["resource"] for e in added if e.type == "story/resource-released"], ["session", "wt"])
        self.assertEqual([e.data["call_id"] for e in added if e.type == "tool/result"], ["c1"])  # c0 has its result
        self.assertEqual([e.data["detail"] for e in added[:2]], ["the run ended without its result (repair)"] * 2)
        self.assertTrue(all(e.data["synthetic"] for e in added))
        self.assertEqual({e.time for e in added}, {run.events[-1].time})
        self.assertFalse(added[-2].data["abandoned"])
        self.assertEqual(sentinel.residuals(fixed)[:2], ("S1: SESSION session RESIDUAL: not released: the run ended "
                                                         "without disposing it (repair)",
                                                         "S1: WORKTREE wt RESIDUAL: not released: the run ended "
                                                         "without disposing it (repair)"))

    def test_repair_is_idempotent_and_byte_identical(self):
        _, text = self.died()
        once = rp.repair(text)
        self.assertEqual(rp.repair(text), once)          # the same journal, twice: the same bytes
        self.assertEqual(rp.repair(once), once)          # a repaired journal has nothing open
        self.assertEqual(rp.closers(reconstruct(once).events), [])
        path = self.root / "journals" / "run-r.jsonl"
        path.write_bytes(path.read_bytes() + b'{"chain":"torn')  # a torn tail is dropped, never an event
        self.assertIs(rp.repair_journal(path), True)
        self.assertEqual(path.read_bytes().decode("utf-8"), once)
        self.assertIs(rp.repair_journal(path), False)

    def test_repair_journal_replaces_durably_or_leaves_the_journal_as_it_was(self):
        _, text = self.died()
        path = self.root / "journals" / "run-r.jsonl"
        before = path.read_bytes()
        with mock.patch.object(rp.os, "fsync", side_effect=OSError("EIO")), self.assertRaisesRegex(OSError, "EIO"):
            rp.repair_journal(path)
        self.assertEqual(path.read_bytes(), before)  # the closers went to a sibling, never over the journal
        tmp = path.with_name(path.name + ".repair")
        with mock.patch.object(rp.os, "write", lambda fd, b: 1), \
                self.assertRaisesRegex(rp.RepairError, "^" + re.escape(f"short write to {tmp}") + "$"):
            rp.repair_journal(path)
        self.assertEqual(path.read_bytes(), before)
        with mock.patch.object(rp, "repair", lambda t: "changed\n" + t), \
                self.assertRaisesRegex(rp.RepairError, "^repair would change an existing event$"):
            rp.repair_journal(path)
        opened, real, native = [], os.open, hasattr(os, "O_BINARY")

        def spy(p, flags, mode=0o777):
            opened.append(flags)
            return real(p, flags if native else flags & ~0x8000, mode)  # on Windows the flag is real, and needed
        with mock.patch.object(os, "O_BINARY", 0x8000, create=True), mock.patch.object(os, "open", spy):
            self.assertIs(rp.repair_journal(path), True)
        self.assertTrue(opened[0] & 0x8000 and opened[0] & os.O_TRUNC and opened[0] & os.O_CREAT)
        self.assertEqual(path.read_bytes().decode("utf-8"), rp.repair(text))

    def test_a_run_already_interrupted_is_abandoned_by_repair(self):
        _, text = self.died(interrupted=True)
        fixed = rp.repair(text)
        added = reconstruct(fixed).events[-1]
        self.assertEqual((added.type, dict(added.data)), ("run/interrupted", {"abandoned": True, "synthetic": True}))
        self.assertEqual(rp.closers(reconstruct(fixed).events), [])  # an abandoned run has nothing open
        self.assertEqual(rp.repair(fixed), fixed)

    def test_closers_are_per_story_in_story_order_at_the_last_real_time(self):
        run, text = self.died(stories=("S5", "S4", "S3", "S2"))
        last = run.events[-1]
        run._writer.close()
        req = next(e for e in run.events if e.type == T.PROVIDER_REQUEST.value)
        w = f3.JournalWriter3(run.journal_path)  # a closer already written, later on the clock than any real event
        w.append(T.PROVIDER_RESULT, {"story_id": "S1", "outcome": "OUTCOME_UNKNOWN", "synthetic": True, "detail": ""},
                 source_seqs=(req.seq,), time=last.time + 50)
        w.close()
        added = reconstruct(rp.repair(run.journal_path.read_bytes().decode("utf-8"))).events[len(run.events) + 1:]
        self.assertEqual([e.data["resource"] for e in added if e.type == "story/resource-released"],
                         ["session", "wt", "wt-S2", "wt-S3", "wt-S4", "wt-S5"])
        self.assertEqual({e.time for e in added}, {last.time})

    def test_repair_refuses_what_it_cannot_extend(self):
        with self.assertRaisesRegex(rp.RepairError, "does not reconstruct"):
            rp.repair("garbage\n")
        from aisef2.journal.writer import JournalWriter
        one = self.root / "one.jsonl"
        w = JournalWriter(one, clock=lambda: 0.0)
        w.append(T.RUN_BEGIN, {"journal_format": 1, "run_id": "r"})
        w.close()
        with self.assertRaisesRegex(rp.RepairError, "a format-1 journal is read, never extended"):
            rp.repair(one.read_text(encoding="utf-8"))
        with self.assertRaisesRegex(rp.RepairError, "format-2 closers"):
            rp.closers(())
        _, text = self.died()
        from aisef2.journal.event import Event, encode, link
        j = reconstruct(text)
        stranger = Event(len(j.events), "report/progress", {}, 0.0, ignorable=True)
        with self.assertRaisesRegex(rp.RepairError, rf"^the journal holds unknown ignorable events \[{stranger.seq}\]: "
                                                    "repair extends only a journal it can read in full$"):
            rp.repair(text + encode(stranger, link(j.head(), stranger)))
        self.assertIsInstance(rp.RepairError("x"), JournalError)


@unittest.skipUnless(POSIX, "a real SIGINT / SIGKILL to a child process (POSIX)")
class RealSignals(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory(prefix="aisef2-sig-")
        self.addCleanup(self._d.cleanup)
        self.root = pathlib.Path(self._d.name)

    def controller(self, info):
        return (f"import json, pathlib, sys\nsys.path.insert(0, {str(ROOT)!r})\n"
                "from aisef2.arch.enums import EventType as T\nfrom aisef2.runtime.run_scope import RunScope\n"
                "from aisef2.runtime.tool import ToolCall\nfrom tests.v2.p4.test_run_scope import plan, spec\n"
                f"run = RunScope({str(self.root)!r}, 'run-s', spec=spec)\nrun.begin()\nplan(run)\n"
                f"run.append(T.STORY_BEGIN, {{'story_id': 'S1', 'parent': {SHA!r}}})\n"
                f"call = ToolCall(run, 'S1', 'c1', 'python', [sys.executable, '-c', {LONG!r}], grace_s=(1.0, 1.0))\n"
                "with run.interruptible():\n    call.dispatch()\n"
                f"    pathlib.Path({str(info)!r}).write_text(json.dumps([call.range.target_pid, call.range.group]))\n"
                "    call.finish(None)\n")

    def start(self):
        info = self.root / "info.json"
        c = subprocess.Popen([PY, "-P", "-c", self.controller(info)])
        self.addCleanup(lambda: c.poll() is None and c.kill())
        deadline = time.monotonic() + 30
        while not (info.exists() and info.read_text()):
            self.assertLess(time.monotonic(), deadline, "the controller never dispatched")
            time.sleep(0.02)
        return c, json.loads(info.read_text())

    def test_SIGINT_mid_story_is_an_interruption_with_no_gap_and_nothing_left_running(self):
        c, (target, group) = self.start()
        c.send_signal(signal.SIGINT)
        self.assertEqual(c.wait(30), 0)
        j = reconstruct((self.root / "journals" / "run-s.jsonl").read_bytes().decode("utf-8"))
        tail = [(e.type, e.data.get("outcome"), e.data.get("status")) for e in j.events[-6:]]
        self.assertEqual(tail, [("tool/invoked", None, None), ("run/interrupted", None, None),
                                ("tool/result", "OUTCOME_UNKNOWN", None), ("story/resource-released", None, "RELEASED"),
                                ("run/dispose-begin", None, None), ("run/end", None, None)])
        self.assertEqual([e.seq for e in j.events], list(range(len(j.events))))
        self.assertEqual(j.events[-1].type, "run/end")
        from aisef2.runtime.process_range import process_table
        self.assertFalse([p for p in process_table().values() if p.group == group])
        self.assertEqual(sentinel.read(self.root / "run.sentinel")["state"], "OPEN")

    def test_SIGKILL_mid_story_leaves_a_journal_that_repair_closes_and_a_tool_that_does_not_survive(self):
        c, (target, group) = self.start()
        c.kill()
        c.wait()
        from aisef2.runtime.process_range import process_table
        deadline = time.monotonic() + 10
        while [p for p in process_table().values() if p.group == group]:  # the anchor's watchdog takes the tool down
            self.assertLess(time.monotonic(), deadline, "the tool outlived its controller")
            time.sleep(0.05)
        path = self.root / "journals" / "run-s.jsonl"
        self.assertTrue(rp.repair_journal(path))
        j = reconstruct(path.read_bytes().decode("utf-8"))
        self.assertEqual([e.type for e in j.events[-4:]], ["tool/result", "story/resource-released",
                                                           "run/interrupted", "run/end"])
        nxt = closed_after(self, RunScope(self.root, "run-n", spec=spec))
        pre = nxt.begin()
        self.assertEqual(pre.previous, "TORN")
        self.assertEqual(pre.residuals, ("S1: PROCESS_RANGE tool c1 RESIDUAL: not released: the run ended without "
                                         "disposing it (repair)",))


if __name__ == "__main__":
    unittest.main()
