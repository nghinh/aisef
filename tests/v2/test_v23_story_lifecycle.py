"""E5 (W1-DESIGN §4.5) — the attempt handler's fault-injection matrix: a fault at any stage either CLOSES the attempt
in the journal (C: synthetic closer, one constant-label row, a false decision citing every check, UNKNOWN, rollback,
dispose, end — then the SAME exception object out of run_story) or PROPAGATES with nothing written (P: H3 repository
state unknown, H5 the closure itself refused, H8 BaseException). This file is the kill file of the lifecycle: it is
appended (round v2.3, read-time) to the kill sets of `_attempt` and `run.py::execute`, and `_Stages.advance` is a new
round target. Fixtures are imported from tests/v2/test_p6_orchestration.py and test_b1gap5_story_runner_attempt.py;
neither file is edited. Temporary directories only — no unlink/rmtree/kill sites (INV-MUTATION-AUTHORITY)."""

import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import EventType as T, ObligationRole  # noqa: E402
from aisef2.errors import InvariantError  # noqa: E402
from aisef2.journal.event import JournalError  # noqa: E402
from aisef2.journal.fold import ProjectionError  # noqa: E402
from aisef2.orchestrate import story_runner as sr  # noqa: E402
from aisef2.orchestrate.quality import TestsPolicy  # noqa: E402
from aisef2.quality import test_execution as te  # noqa: E402
from aisef2.runtime import sentinel  # noqa: E402
from aisef2.runtime.run_scope import RunScope  # noqa: E402
from tests.v2 import test_p6_orchestration as O  # noqa: E402
from tests.v2.p4.test_run_scope import spec as RUN_SPEC  # noqa: E402
from tests.v2.p4.world import closed_after  # noqa: E402
from tests.v2.test_b1gap5_story_runner_attempt import EscapedDev  # noqa: E402


class Boom(RuntimeError):
    """The injected foreign fault."""


class Base(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        d = tempfile.TemporaryDirectory(prefix="aisef2-e5-")
        self.addCleanup(d.cleanup)
        self.tmp = pathlib.Path(d.name)
        self.repo, self.base = O.make_repo(self.tmp)
        for sub in ("ws", "merge", "run"):
            (self.tmp / sub).mkdir()
        self.script = str(self.tmp / "scan.py")
        pathlib.Path(self.script).write_text(O.SCAN_SCRIPT, encoding="utf-8")
        self.ws = O.GitWorkspace(self.repo, self.tmp / "ws")
        self.merger = O.GitMerger(self.repo, "main", self.tmp / "merge")
        self.clock = iter(float(n) for n in range(10 ** 6))
        self.run = closed_after(self, RunScope(self.tmp / "run", "run-e5", spec=RUN_SPEC, clock=lambda: next(self.clock)))
        self.run.begin()
        self.c1, self.s1 = O.contract("C1", "app.calc:add", [1, 2], 3)
        self.specs = {self.s1.id: self.s1}
        self.plan = O.plan_of(self.base, O.obligation("C-1", self.s1.id, "S1", ObligationRole.INTRODUCE), pid="PLAN-E5")

    # ---- helpers -------------------------------------------------------------------------------------------------
    def dev(self):
        return O.Dev({"app/calc.py": O.CALC + O.ADD, "tests/test_s1.py": O.TEST_ADD})

    def go(self, dev=None, *, workspace=None, merger=None, reviewer=None, scanner=None):
        inputs = sr.StoryInputs(self.specs, O.PROBE, O.ENV, te.DeveloperTests("S1", ("tests/test_s1.py",)),
                                te.DeveloperTests("S1", ("tests/test_other.py",)),
                                te.Dependencies(frozenset(), frozenset({"app", "tests"})), te.UNITTEST)
        adapters = sr.Adapters(dev or self.dev(), reviewer or O.Rev(), scanner or O.Scan(self.script),
                               merger or self.merger, workspace or self.ws)
        return sr.run_story(self.run, self.plan, "S1", inputs, adapters,
                            sr.Policy(O.LIMITS, TestsPolicy(True), tool_timeout_s=60))

    def raising(self, fault, **kw):
        """run_story under the injected fault: asserts the SAME object propagates and returns it."""
        with self.assertRaises(type(fault)) as ctx:
            self.go(**kw)
        self.assertIs(ctx.exception, fault)
        return ctx.exception

    def events(self, kind=None):
        return [e for e in self.run.events if kind is None or e.type == kind]

    def attempt_events(self):
        begin = max(i for i, e in enumerate(self.run.events) if e.type == T.STORY_BEGIN.value)
        return list(self.run.events)[begin:]

    def contained(self, stage: str, label: str, exc_name: str = "Boom"):
        """The C tail of §4.5: the row, the false decision citing every check, UNKNOWN, rollback, dispose, end."""
        tail = self.attempt_events()
        detail = f"{stage} raised {exc_name}"
        rows = [e for e in tail if e.type == T.GATE_CHECK.value]
        self.assertTrue(rows, "no gate/check rows in the attempt")
        last = rows[-1]
        self.assertEqual((last.data["check"], last.data["passed"], last.data["detail"]), (f"S1:{label}", False, detail))
        (decision,) = [e for e in tail if e.type == T.GATE_DECISION.value]
        self.assertFalse(decision.data["passed"])
        self.assertEqual(list(decision.source_seqs), [e.seq for e in rows])
        (observed,) = [e for e in tail if e.type == T.FAILURE_OBSERVED.value]
        self.assertEqual((observed.data["code"], observed.data["owner"], observed.data["retryable"],
                          observed.data["original"]), ("UNKNOWN", "INTEGRATION", False, exc_name))
        kinds = [e.type for e in tail]
        for kind in ("story/rollback", "story/dispose", "story/end"):
            self.assertIn(kind, kinds, kinds)
        self.assertLess(kinds.index("story/rollback"), kinds.index("story/dispose"))
        self.assertLess(kinds.index("story/dispose"), kinds.index("story/end"))
        self.assertEqual(self.run.open_stories(), [])
        self.run.shutdown()

    def propagated(self):
        """The P tail of §4.5: the story open; interrupt() closes and ends the run."""
        kinds = [e.type for e in self.attempt_events()]
        for kind in ("gate/decision", "failure/observed", "story/rollback", "story/dispose", "story/end"):
            self.assertNotIn(kind, kinds, kinds)
        self.assertEqual(self.run.open_stories(), ["S1"])
        self.run.interrupt()
        self.assertEqual(self.run.events[-1].type, T.RUN_END.value)

    def closer(self):
        return [e for e in self.attempt_events() if e.type == T.PROVIDER_RESULT.value and e.data.get("synthetic")]

    def residuals(self):
        return sentinel.residuals(self.run.journal_path.read_text(encoding="utf-8"))

    def deny(self, event_type, when=None):
        """run.append refusing one event type (§4.5 'a run.append wrapper that raises JournalError'); `when` narrows
        the refusal to matching payloads (a handler row, never the body's own)."""
        orig = self.run.append

        def wrapper(t, data, source_seqs=()):
            if t is event_type and (when is None or when(data)):
                raise JournalError(f"injected: {t.value} refused")
            return orig(t, data, source_seqs=source_seqs)
        return mock.patch.object(self.run, "append", side_effect=wrapper)


class Contained(Base):
    """The C rows of the matrix: a foreign fault closes the attempt and re-raises the same object."""

    def test_the_success_path_still_commits(self):
        result = self.go()
        self.assertEqual([a.outcome for a in result.attempts], ["COMMIT"])
        self.assertEqual(self.run.open_stories(), [])
        self.run.shutdown()
        self.assertEqual(self.residuals(), ())

    def test_f1_a_fault_in_acquire_is_contained_with_the_resources_row(self):
        fault = Boom("E5")
        with mock.patch.object(self.ws, "scratch", side_effect=fault):
            self.raising(fault)
        self.contained("ACQUIRE", "resources")
        self.assertEqual(self.residuals(), ())

    def test_f2_a_fault_on_the_second_checkout_releases_the_scratch(self):
        fault = Boom("E5")
        real = self.ws.checkout
        calls = []

        def second_raises(name, rev):
            calls.append(name)
            if len(calls) == 2:
                raise fault
            return real(name, rev)
        with mock.patch.object(self.ws, "checkout", side_effect=second_raises):
            self.raising(fault)
        self.contained("ACQUIRE", "resources")
        released = [e.data["resource"] for e in self.events("story/resource-released")]
        self.assertIn("scratch-S1", released)
        self.assertEqual(self.residuals(), ())

    def test_f3_a_fault_in_admission_is_contained(self):
        fault = Boom("E5")
        with mock.patch.object(sr, "admit_story", side_effect=fault):
            self.raising(fault)
        self.contained("ADMIT", "admission")

    def test_f4_a_fault_in_continuation_is_contained_under_the_admission_label(self):
        fault = Boom("E5")
        with mock.patch.object(sr, "continue_story", side_effect=fault):
            self.raising(fault)
        self.contained("CONTINUE", "admission")

    def test_f5_a_developer_fault_closes_its_open_request_first(self):
        fault = Boom("E5")

        class RaisingDev(O.Dev):
            def implement(self, story_id, criteria, checkout):
                raise fault
        self.raising(fault, dev=RaisingDev())
        (closer,) = self.closer()
        self.assertEqual((closer.data["outcome"], closer.data["detail"]),
                         ("OUTCOME_UNKNOWN", "DEVELOP raised Boom before its result"))
        (request,) = [e for e in self.attempt_events() if e.type == T.PROVIDER_REQUEST.value]
        self.assertEqual(tuple(closer.source_seqs), (request.seq,))
        self.contained("DEVELOP", "developer")
        self.assertNotIn("has no result", " ".join(self.residuals()))

    def test_f6_a_range_escape_is_contained_and_every_writable_resource_is_residual(self):
        try:
            self.go(dev=EscapedDev())
        except sr.RangeEscaped as e:
            escaped = e   # hold the traceback: the attempt frame keeps the unreleased handles alive, as a real
        else:             # interrupted process would — nothing here RELEASED them (the journal says RESIDUAL)
            self.fail("RangeEscaped did not propagate")
        for name in ("scratch-S1", "wt-S1", "verifier-wt-S1"):
            self.assertTrue(list(self.tmp.glob(f"ws/{name}*")), name)
        del escaped
        self.contained("DEVELOP", "developer", exc_name="RangeEscaped")
        res = self.residuals()
        self.assertEqual(len(res), 4, res)
        self.assertTrue(any("developer S1 range" in r for r in res), res)
        for name in ("scratch-S1", "wt-S1", "verifier-wt-S1"):
            self.assertTrue(any(name in r for r in res), (name, res))

    def test_f7_a_fault_moving_the_candidate_is_contained(self):
        fault = Boom("E5")
        real = self.ws.move
        with mock.patch.object(self.ws, "move", side_effect=lambda *a: (_ for _ in ()).throw(fault)):
            self.raising(fault)
        self.assertIs(real, self.ws.move.__wrapped__ if hasattr(self.ws.move, "__wrapped__") else real)
        self.contained("MOVE_CANDIDATE", "candidate")

    def test_f8_a_fault_in_prove_is_contained(self):
        fault = Boom("E5")
        with mock.patch.object(sr, "prove", side_effect=fault):
            self.raising(fault)
        self.contained("PROVE_CANDIDATE", "candidate")

    def test_f9_a_fault_in_assess_is_contained_and_test_ranges_release_first(self):
        fault = Boom("E5")
        with mock.patch.object(sr, "assess", side_effect=fault):
            self.raising(fault)
        self.contained("QUALITY", "quality")
        kinds = [e.type for e in self.attempt_events()]
        row = next(i for i, e in enumerate(self.attempt_events())
                   if e.type == T.GATE_CHECK.value and e.data["check"] == "S1:quality")
        self.assertNotIn("story/resource-released", kinds[row:kinds.index("story/dispose")])

    def test_f10_review_and_scan_faults_are_contained_and_unconfine_runs_once(self):
        real = sr.unconfine
        for callee in ("review", "scan"):
            with self.subTest(callee):
                self.setUp()
                fault = Boom("E5")
                calls = []

                def spy(c, _calls=calls):
                    _calls.append(1)
                    return real(c)
                with mock.patch.object(sr, callee, side_effect=fault), \
                        mock.patch.object(sr, "unconfine", side_effect=spy):
                    self.raising(fault)
                self.contained("REVIEW_SCAN", "review")
                self.assertEqual(len(calls), 1)

    def test_f13_a_foreign_post_merge_fault_reverts_this_attempts_merge(self):
        fault = Boom("E5")
        real = self.ws.move
        moved = []

        def move(wt, rev):
            moved.append(rev)
            if len(moved) > 2:   # the two candidate moves succeeded; the merged moves raise
                raise fault
            return real(wt, rev)
        reverted = []
        real_revert = self.merger.revert
        with mock.patch.object(self.ws, "move", side_effect=move), \
                mock.patch.object(self.merger, "revert", side_effect=lambda rev: reverted.append(rev) or real_revert(rev)):
            self.raising(fault)
        self.assertEqual(len(reverted), 1)
        main = O.git(self.repo, "rev-parse", "main").stdout.strip()
        self.assertEqual(main, self.base)
        self.contained("POST_MERGE", "post-merge")

    def test_f14_a_reprove_fault_reverts_once_then_contains(self):
        fault = Boom("E5")
        reverted = []
        real_revert = self.merger.revert
        with mock.patch.object(sr, "reprove", side_effect=fault), \
                mock.patch.object(self.merger, "revert", side_effect=lambda rev: reverted.append(rev) or real_revert(rev)):
            self.raising(fault)
        self.assertEqual(len(reverted), 1)
        self.assertEqual(O.git(self.repo, "rev-parse", "main").stdout.strip(), self.base)
        self.contained("POST_MERGE", "post-merge")


class ContainedToolCall(Base):
    """F11: `ToolCall.finish` raising after dispatch — contained, with the open call a DECLARED residual that a
    later interrupt closes without error (its closer belongs to the ToolCall, never to E5: a journal-derived closer
    would make the interrupt write it twice)."""

    def test_f11_a_finish_fault_is_contained_and_the_open_call_is_declared(self):
        from aisef2.runtime.tool import ToolCall
        fault = Boom("E5")
        with mock.patch.object(ToolCall, "finish", side_effect=fault, autospec=True):
            self.raising(fault)
        tail = self.attempt_events()
        rows = [e for e in tail if e.type == T.GATE_CHECK.value]
        self.assertEqual((rows[-1].data["check"], rows[-1].data["passed"], rows[-1].data["detail"]),
                         ("S1:review", False, "REVIEW_SCAN raised Boom"))
        (decision,) = [e for e in tail if e.type == T.GATE_DECISION.value]
        self.assertFalse(decision.data["passed"])
        kinds = [e.type for e in tail]
        for kind in ("story/rollback", "story/dispose", "story/end"):
            self.assertIn(kind, kinds)
        self.assertEqual(self.run.open_stories(), [])
        self.assertTrue(any("has no result" in r for r in self.residuals()), self.residuals())
        self.run.interrupt()   # closes the dispatched call with its own synthetic closer, exactly once
        closers = [e for e in self.run.events if e.type == T.TOOL_RESULT.value and e.data.get("synthetic")]
        self.assertEqual(len(closers), 1)
        self.assertEqual(self.run.events[-1].type, T.RUN_END.value)


class ContainedPostMerge(Base):
    """F15: B7 — a reprove fault with merged == candidate never reverts; the attempt still closes."""

    def test_f15_b7_no_commit_to_undo_means_no_revert(self):
        from types import SimpleNamespace
        fault = Boom("E5")
        real_merge = sr.merge

        def ff(run, story_id, merger, candidate):   # the merge git made no commit for: merged == candidate (B7)
            m = real_merge(run, story_id, merger, candidate)
            return SimpleNamespace(check=m.check, failure=m.failure, merge=SimpleNamespace(revision=candidate))
        reverted = []
        with mock.patch.object(sr, "merge", side_effect=ff), \
                mock.patch.object(sr, "reprove", side_effect=fault), \
                mock.patch.object(self.merger, "revert", side_effect=lambda rev: reverted.append(rev)):
            self.raising(fault)
        self.assertEqual(reverted, [])
        self.contained("POST_MERGE", "post-merge")


class Propagated(Base):
    """The P rows: H3 (repository state unknown), H5 (the closure refused), H8 (BaseException)."""

    def test_f12_a_merge_fault_propagates_with_no_outcome(self):
        fault = Boom("E5")
        with mock.patch.object(sr, "merge", side_effect=fault):
            self.raising(fault)
        self.propagated()

    def test_f16_a_typed_post_merge_failure_whose_revert_raises_propagates_h3(self):
        fault = Boom("revert residual")
        real = self.ws.move
        moved = []

        def move(wt, rev):
            moved.append(rev)
            if len(moved) > 2:
                raise sr.ResourceUnavailable("merged checkout refused")   # the TYPED post-merge failure
            return real(wt, rev)
        with mock.patch.object(self.ws, "move", side_effect=move), \
                mock.patch.object(self.merger, "revert", side_effect=fault):
            self.raising(fault)
        tail = self.attempt_events()
        self.assertEqual(tail[-1].type, T.GATE_CHECK.value)   # the typed post-merge row is the last event
        self.assertEqual(tail[-1].data["check"], "S1:post-merge")
        self.assertEqual(self.run.open_stories(), ["S1"])
        self.run.interrupt()
        self.assertEqual(self.run.events[-1].type, T.RUN_END.value)

    def test_f17_a_refused_decision_propagates_with_nothing_more(self):
        with self.deny(T.GATE_DECISION):
            with self.assertRaises(JournalError):
                self.go()
        self.propagated()

    def test_f18_a_refused_commit_leaves_the_true_decision_last_and_no_rollback(self):
        with self.deny(T.STORY_COMMIT):
            with self.assertRaises(JournalError):
                self.go()
        tail = self.attempt_events()
        self.assertEqual(tail[-1].type, T.GATE_DECISION.value)
        self.assertTrue(tail[-1].data["passed"])
        self.assertNotIn("story/rollback", [e.type for e in tail])
        self.run.interrupt()

    def test_f19_a_refused_dispose_leaves_the_scope_active(self):
        with self.deny(T.STORY_DISPOSE):
            with self.assertRaises(JournalError):
                self.go()
        kinds = [e.type for e in self.attempt_events()]
        self.assertIn("story/commit", kinds)
        self.assertNotIn("story/dispose", kinds)
        self.assertEqual(self.run.open_stories(), ["S1"])
        self.run.interrupt()
        self.assertEqual(self.run.events[-1].type, T.RUN_END.value)

    def test_f20_a_release_that_raises_invariant_error_stops_after_dispose(self):
        real = self.ws.scratch

        class BadRelease:
            def __init__(self, inner):
                self._inner, self.name, self.kind, self.path = inner, inner.name, inner.kind, inner.path

            def release(self):
                raise InvariantError("release refused (E5 F20)")
        with mock.patch.object(self.ws, "scratch", side_effect=lambda name: BadRelease(real(name))):
            with self.assertRaises(InvariantError):
                self.go()
        kinds = [e.type for e in self.attempt_events()]
        self.assertIn("story/dispose", kinds)
        self.assertNotIn("story/end", kinds)
        self.run.interrupt()   # resumes the rest of the disposal and ends the run
        self.assertEqual(self.run.events[-1].type, T.RUN_END.value)

    def test_f21_a_refused_end_leaves_the_story_at_dispose(self):
        with self.deny(T.STORY_END):
            with self.assertRaises(JournalError):
                self.go()
        kinds = [e.type for e in self.attempt_events()]
        self.assertIn("story/dispose", kinds)
        self.assertNotIn("story/end", kinds)
        self.run.interrupt()
        self.assertEqual(self.run.events[-1].type, T.RUN_END.value)

    def test_f22_an_invariant_error_in_prove_propagates_untouched(self):
        fault = InvariantError("E5 probe invariant")
        with mock.patch.object(sr, "prove", side_effect=fault):
            with self.assertRaises(InvariantError) as ctx:
                self.go()
        self.assertIs(ctx.exception, fault)
        kinds = [e.type for e in self.attempt_events()]
        for kind in ("gate/decision", "failure/observed", "story/rollback"):
            self.assertNotIn(kind, kinds)
        self.run.interrupt()

    def test_f23_a_keyboard_interrupt_writes_nothing_and_the_run_interrupts(self):
        fault = KeyboardInterrupt()

        class KIDev(O.Dev):
            def implement(self, story_id, criteria, checkout):
                raise fault
        with self.run.interruptible():
            self.go(dev=KIDev())
        kinds = [e.type for e in self.run.events]
        self.assertIn("run/interrupted", kinds)
        self.assertEqual(self.run.events[-1].type, T.RUN_END.value)
        synthetic = [e for e in self.run.events if e.type == T.PROVIDER_RESULT.value and e.data.get("synthetic")]
        self.assertEqual(len(synthetic), 1)
        self.assertNotIn("story/rollback", kinds)

    def test_f24_a_refused_check_inside_the_handler_propagates_the_original_with_a_note(self):
        fault = Boom("E5")

        class RaisingDev(O.Dev):
            def implement(self, story_id, criteria, checkout):
                raise fault
        with self.deny(T.GATE_CHECK, when=lambda data: data["detail"].startswith("DEVELOP raised")):
            with self.assertRaises(Boom) as ctx:
                self.go(dev=RaisingDev())
        self.assertIs(ctx.exception, fault)
        notes = getattr(ctx.exception, "__notes__", [])
        self.assertTrue(any(n.startswith("E5: the attempt could not be closed: JournalError: ") for n in notes),
                        notes)   # H6 prescribes the note verbatim: prefix, the later type, ": ", then its text
        self.assertEqual(len([e for e in self.attempt_events()
                              if e.type == T.PROVIDER_RESULT.value and e.data.get("synthetic")]), 1)
        self.assertNotIn("gate/decision", [e.type for e in self.attempt_events()])
        self.run.interrupt()

    def test_f25_a_refused_rollback_propagates_the_original_and_unknown_is_last(self):
        fault = Boom("E5")

        class RaisingDev(O.Dev):
            def implement(self, story_id, criteria, checkout):
                raise fault
        with self.deny(T.STORY_ROLLBACK):
            with self.assertRaises(Boom) as ctx:
                self.go(dev=RaisingDev())
        self.assertIs(ctx.exception, fault)
        notes = getattr(ctx.exception, "__notes__", [])
        self.assertTrue(any(n.startswith("E5: the attempt could not be closed: JournalError: ") for n in notes),
                        notes)   # H6's verbatim note format, on the closure path too
        self.assertEqual(self.run.events[-1].type, T.FAILURE_OBSERVED.value)
        self.run.interrupt()


class Guard(Base):
    """G1/G2: the stage guard and the three independent double-dispose refusals."""

    def test_g1_the_guard_refuses_a_backwards_move_and_a_second_dispose(self):
        st = sr._Stages()
        st.advance(sr.Stage.DEVELOP)
        n = len(self.run.events)
        with self.assertRaises(InvariantError):
            st.advance(sr.Stage.ADMIT)
        st2 = sr._Stages()
        st2.advance(sr.Stage.DISPOSE)
        with self.assertRaises(InvariantError):
            st2.advance(sr.Stage.DISPOSE)
        self.assertEqual(len(self.run.events), n)

    def test_g2_a_second_dispose_is_refused_three_ways(self):
        self.go()
        scope = self.run.story("S1")
        n = len(self.run.events)
        with self.assertRaises(ProjectionError):
            self.run.append(T.STORY_DISPOSE, {"story_id": "S1"})
        report = scope.dispose()
        self.assertEqual(len(self.run.events), n)
        self.assertEqual(report, scope.dispose())
        self.run.shutdown()


@unittest.skipUnless(os.name == "posix", "reuses the demo's shebang-started fake developer (as test_b1gap4 does)")
class RunExecute(unittest.TestCase):
    """R1: a story E5 closes inside a REAL `run.execute` — RUN.json carries the journal's words, the error is named,
    and verify no longer reports "the record's story outcomes are not the journal's" (W1-DESIGN §4.4's run.py hunk)."""

    def test_r1_execute_records_the_journals_words_for_a_closed_raising_story(self):
        from aisef2.app import demo, settings
        from aisef2.app import run as R
        from aisef2.app import verify as V
        td = tempfile.TemporaryDirectory(prefix="aisef-e5-r1-")
        self.addCleanup(td.cleanup)
        t = pathlib.Path(td.name)
        (t / "xdg" / "opencode").mkdir(parents=True)
        (t / "xdg" / "opencode" / "opencode.json").write_text(json.dumps(
            {"provider": {"fakeprov": {"options": {"baseURL": demo.SETTINGS["provider"]["endpoint"],
                                                   "apiKey": "{env:AISEF_DEMO_NO_KEY}"}}}}), encoding="utf-8")
        client_exe = t / "client" / "opencode"
        client_exe.parent.mkdir()
        client_exe.write_text(f"#!{sys.executable}\nBODIES = {demo.BODIES!r}\nTEST = {demo.TEST!r}\n" + demo.FAKE_CLIENT)
        client_exe.chmod(0o755)
        (client_exe.parent / "mode").write_text("correct")
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(t / "xdg")}):
            project, source = demo.build(t)
        fault = RuntimeError("E5 R1")
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(t / "xdg")}), \
                mock.patch.object(sr, "prove", side_effect=fault):
            rec = R.execute(project, settings.load(demo.SETTINGS), source, t / "out",
                            client_exe=str(client_exe), transport=demo.loopback())
        self.assertEqual(rec["story_outcomes"].get("S1"), ["ROLLBACK"], rec["story_outcomes"])
        self.assertTrue(any(err["story"] == "S1" and "RuntimeError" in err["error"] for err in rec["story_errors"]),
                        rec["story_errors"])
        report = V.verify(project, t / "out")
        self.assertFalse([p for p in report.get("problems", []) if "story outcomes are not the journal's" in p],
                         report.get("problems"))


if __name__ == "__main__":
    unittest.main()
