"""V2.1 mutation survivors, batch T18a — the controller script (`HARNESS`) of `probe.python_callable_v2`.

Each class states one requirement of the controller and the survivors of campaign 2 it pins
(`aisef2/probe/python_callable_v2.py::HARNESS/<function> [index]`).

* an answer on the subject's channel that the agent did not write is never trusted and never blamed on the
  environment, at whichever point of the exchange it arrives (`answer_to`, `answered`, `ended`, `finish`);
* a failure of the subject's process in an operation is a harness failure that names its type, not a verdict;
* a subject process that ended by a signal is never a verdict (RFC section 9.3);
* a module with no `__file__` is judged by its `__path__` (`inside`);
* the controller's own lifecycle: the protocol it writes ends with END, and it ends by itself once it has reported.

The fixtures are real checkouts run by the real probe (subject process included); the two lifecycle properties run
the controller as a process of its own on a hand-built request, as the probe does, and read its marker file.
"""

import json
import os
import pathlib
import secrets
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict, ProbeExecutionStatus, SubjectAbsence  # noqa: E402
from aisef2.probe import cli_invocation as ci, python_callable as pc, python_callable_v2 as pc2  # noqa: E402
from aisef2.probe.protocol import ObservationKind as K, RevisionRef, run_probe  # noqa: E402
from aisef2.product.outcome import Executed, IndeterminateReason  # noqa: E402
from aisef2.runtime.process_range import ProcessRange  # noqa: E402
from tests.v2 import test_python_callable_v2 as base  # noqa: E402

S, R, I = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED, BehaviorVerdict.INDETERMINATE
PA, NCS = IndeterminateReason.PRECONDITION_ABSENT, IndeterminateReason.NON_CONTROLLER_SIGNAL
REQUIRES = SubjectAbsence.REQUIRES_SUBJECT


def _stray(name: str, line: str, then: str = "") -> str:
    """A subject whose import writes `line` on the agent's own channel (`__main__.WOUT`, the descriptor the agent
    answers on) before the import's own answer, as app/forge.py's `stray` does at call time."""
    return ("import os\nimport __main__\n"
            f"line = {line}\n"
            "os.write(__main__.WOUT, line)\n" + then + "\n\ndef f():\n    return 1\n").replace("NAME", name)


#: another request's number (the import is request 1), shaped like the agent's answer for an absent module
_ABSENCE = ("(__import__('json').dumps({'raised': 'ModuleNotFoundError', 'missing': 'NAME', 'n': 99}) + '\\n')"
            ".encode()")
PRODUCT = {
    "app/__init__.py": "",
    "app/calc.py": base.PRODUCT["app/calc.py"],
    # (a) a well-formed answer carrying another request's number, then the import goes on and answers for itself
    "app/stray_early.py": _stray("app.stray_early", _ABSENCE),
    # (a) the same, then the subject's process ends: nothing of the agent's own follows the forged line
    "app/stray_exit.py": _stray("app.stray_exit", _ABSENCE, "os._exit(0)\n"),
    # (b) a line that is not JSON
    "app/stray_text.py": _stray("app.stray_text", "b'this is not an answer\\n'"),
    # the agent's closing answer is something other than its request number, with nothing else queued
    "app/badbye.py": "import __main__\n\n\ndef f():\n    __main__.OPS['bye'] = lambda r: {'extra': 1}\n    return 1\n",
    "app/honest.py": "def f():\n    return 1\n",
    # the module replaces its own sys.modules entry with an object that has no namespace: `vars()` raises TypeError
    "app/selfswap.py": "import sys\nsys.modules[__name__] = object()\n\n\ndef f():\n    return 1\n",
    # the subject's process ends itself by a signal (raise_signal signals the calling process and no other)
    "app/selfkill.py": "import signal\nsignal.raise_signal(signal.SIGKILL)\n\n\ndef f():\n    return 1\n",
    # a namespace package inside the checkout (no __init__.py): no __file__, a __path__ inside the revision
    "app/ns/data.txt": "x\n",
}


class _Revision(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = tempfile.TemporaryDirectory(prefix="aisef2-kills3-")
        cls.addClassCleanup(scratch.cleanup)
        for rel, text in PRODUCT.items():
            path = pathlib.Path(scratch.name, rel)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        cls.root = scratch.name
        cls.at = RevisionRef(base.SHA, scratch.name)

    def see(self, s):
        return base.P.observe(s, self.at, base.env())

    def run_(self, s):
        return run_probe(base.P, s, self.at, base.env()).result

    def assertTampered(self, seen):
        """`seen` is the observation of a subject that tampered with its channel — REFUTED, the facts its marker and
        the reason it carries (what an operator reads of it) — and returns that reason."""
        self.assertEqual((seen.kind, seen.verdict), (K.OBSERVED, R), seen)
        facts = json.loads(seen.detail)
        self.assertEqual(facts.get("subject"), "present", seen)   # found: it is not the absence the stray claims
        self.assertIsInstance(facts.get("tampered"), str, seen)   # the marker `_concluded` decides on, with its reason
        return facts["tampered"]


class AnswerNotTheAgents(_Revision):
    """B1: every answer on the subject's channel must be the agent's, echoing its request's number. One that is not is
    REFUTED (`tampered`) — not trusted as the operation's answer, not read as the absence it may claim, not an
    environment failure — here when it arrives BEFORE the operation's own answer, which the existing closing-exchange
    case cannot reach (its stray carries the call's own number and is judged at the closing exchange).

    `stray_exit` forges an absence under another request's number and then ends its process, so that nothing of the
    agent's own follows it: a controller that took it for the import's answer would report SUBJECT_ABSENT, which a
    REQUIRES_SUBJECT proof reads as INDETERMINATE (the precondition absent) instead of the developer's REFUTED.

    Pins aisef2/probe/python_callable_v2.py::HARNESS/answer_to [4, 8, 9], HARNESS/answered [6] and
    HARNESS/ended [1, 6, 7, 14, 15, 16, 24, 25, 26, 29]."""

    def test_a_stray_before_the_operations_own_answer_is_REFUTED_not_trusted_and_not_blamed_on_the_environment(self):
        for locator in ("app.stray_early:f", "app.stray_exit:f", "app.stray_text:f"):
            with self.subTest(locator=locator):
                self.assertTampered(self.see(base.spec(locator, {"returns": 1})))
                # never read as the absence it claims, never charged to the environment
                self.assertEqual(self.run_(base.spec(locator, {"returns": 1}, absence=REQUIRES)), Executed(R))


class ClosingExchange(_Revision):
    """The closing exchange checks the SHAPE of the agent's last answer on its own: exactly its request number. A
    subject that makes it carry anything else does not get the verdict its call earned, though nothing else is
    queued on the channel (the existing stray case also deviates in the queue, which is a race). The reason it gives
    is the one the detection before an operation's answer gives: one reason at every detection point.

    Pins aisef2/probe/python_callable_v2.py::HARNESS/finish [5] and HARNESS/answer_to [10]."""

    def test_a_closing_answer_that_is_not_exactly_its_number_is_REFUTED_whatever_else_is_queued(self):
        self.assertEqual(self.run_(base.spec("app.honest:f", {"returns": 1})), Executed(S))
        s = base.spec("app.badbye:f", {"returns": 1})
        self.assertTampered(self.see(s))
        self.assertEqual(self.run_(s), Executed(R))

    def test_the_reason_is_the_same_at_the_closing_exchange_and_before_an_operations_answer(self):
        closing = self.assertTampered(self.see(base.spec("app.badbye:f", {"returns": 1})))
        self.assertTrue(closing)   # an equality of two empty reasons would prove nothing
        for locator in ("app.stray_early:f", "app.stray_text:f"):
            with self.subTest(locator=locator):
                self.assertEqual(self.assertTampered(self.see(base.spec(locator, {"returns": 1}))), closing)


class OperationFailure(_Revision):
    """A subject that makes the agent's own operation fail (`vars()` of a module that replaced itself by an object
    raises TypeError, answered as `agent_failure`) is a failure of the observation, not the developer's: HARNESS_FAILED
    naming the failure type, UNRUNNABLE to the run (routed to the environment) — never a verdict on the product, never
    the controller's own KeyError, never "ended without a result".

    Pins aisef2/probe/python_callable_v2.py::HARNESS/answered [7] and HARNESS/ended [2, 8, 17, 30]."""

    def test_the_failure_is_the_harnesss_and_names_its_type(self):
        s = base.spec("app.selfswap:f", {"returns": 1})
        seen = self.see(s)
        self.assertEqual((seen.kind, seen.verdict), (K.HARNESS_FAILED, None), seen)
        self.assertIn("TypeError", seen.detail)
        result = self.run_(s)
        self.assertIs(result.status, ProbeExecutionStatus.UNRUNNABLE)
        self.assertIn("TypeError", result.detail)


@unittest.skipUnless(os.name == "posix", "a signal-ended process (SIGKILL) is POSIX")
class SubjectEndedBySignal(_Revision):
    """RFC section 9.3: a subject process that ends by a signal the controller did not send is never a verdict — the
    observation is NON_CONTROLLER_SIGNAL naming the signal, INDETERMINATE to the run, for every class alike. The
    existing cases inject the controller's RESULT; none lets the real controller meet a signalled process.

    Pins aisef2/probe/python_callable_v2.py::HARNESS/ended [10, 18, 28]."""

    def test_a_process_that_signals_itself_is_NON_CONTROLLER_SIGNAL_never_a_verdict(self):
        seen = self.see(base.spec("app.selfkill:f", {"condition": "exists"}))
        self.assertEqual((seen.kind, seen.verdict), (K.NON_CONTROLLER_SIGNAL, None), seen)
        self.assertIn("signal 9", seen.detail)
        for observable in ({"condition": "exists"}, {"returns": 1}, {"blocks": True}):
            with self.subTest(observable=observable):
                self.assertEqual(self.run_(base.spec("app.selfkill:f", observable)), Executed(I, NCS))


class ModuleWithoutFile(_Revision):
    """A module that has no `__file__` is judged by its `__path__`: a builtin has neither, so it resolves only outside
    the revision (as `json:dumps` does); a namespace package of the checkout is inside by its `__path__`.

    Pins aisef2/probe/python_callable_v2.py::HARNESS/inside [3]."""

    def test_neither_file_nor_path_is_outside_the_revision_like_any_module_outside_it(self):
        outside = self.see(base.spec("json:dumps", absence=REQUIRES))
        self.assertEqual((outside.kind, outside.verdict), (K.SUBJECT_ABSENT, R))
        s = base.spec("builtins:len", absence=REQUIRES)
        self.assertEqual(self.see(s), outside)
        self.assertEqual(self.run_(s), Executed(I, PA))

    def test_a_namespace_package_of_the_checkout_is_inside_by_its_path(self):
        self.assertEqual(self.run_(base.spec("app.ns:__path__", absence=REQUIRES)), Executed(S))


class _Controller(unittest.TestCase):
    """The controller as a process of its own on a hand-built request (the probe's own, `pc2._harness_argv`), the real
    subject process (`ci.AGENT`) and the real range; the marker file is read with the probe's own reader."""

    def start(self, locator, cls, window, **stim):
        scratch = tempfile.TemporaryDirectory(prefix="aisef2-kills3-ctl-")
        self.addCleanup(scratch.cleanup)   # runs after the range's release (cleanups are last in, first out)
        work, root = (os.path.realpath(os.path.join(scratch.name, d)) for d in ("work", "root"))
        for rel, text in (("app/__init__.py", ""), ("app/calc.py", base.PRODUCT["app/calc.py"])):
            os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
            pathlib.Path(root, rel).write_text(text, encoding="utf-8")
        self.nonce, self.key = secrets.token_hex(16), secrets.token_hex(32)
        ask, self.proto = os.path.join(work, "request.json"), os.path.join(work, "protocol.log")
        pycache, tmp = os.path.join(work, "pycache"), os.path.join(work, "tmp")
        for d in (work, pycache, tmp):
            os.mkdir(d)
        request = {"mark": pc._MARK, "nonce": self.nonce, "key": self.key, "root": root, "locator": locator,
                   "cls": cls, "args": stim.get("args", []), "kwargs": {}, "attrs": [], "protocol": self.proto,
                   "work": work, "interpreter": sys.executable, "agent": ci.AGENT, "agent_pycache": pycache,
                   "env": {**pc._scrubbed_env(), "TMPDIR": tmp, "TEMP": tmp, "TMP": tmp}, "window": window}
        pathlib.Path(ask).write_text(json.dumps(request), encoding="utf-8")
        with open(os.path.join(work, "harness.log"), "wb") as log:
            run = ProcessRange("controller test", pc2._harness_argv(sys.executable, ask, pycache), cwd=root,
                               env=pc._scrubbed_env(), output=log)
            run.start()
        self.addCleanup(run.release)
        return run

    def tags(self):
        """The tags of the marker file's lines in the order they were written (the controller alone writes it here)."""
        text = pathlib.Path(self.proto).read_text(encoding="utf-8")
        return [line.split(" ")[1] for line in text.splitlines()]

    def until(self, run, tag, seconds=20):
        """Wait for an authentic `tag` line or the controller's exit; the bound is a watchdog, not an assertion."""
        return ci._await(run, self.proto, self.nonce, self.key, tag, time.monotonic() + seconds)


class ControllerLifecycle(_Controller):
    """Pins aisef2/probe/python_callable_v2.py::HARNESS/conclude [3] and HARNESS/deadline [0]."""

    def test_the_protocol_of_a_deadline_ends_with_an_authenticated_END(self):
        """RESULT {"deadline": true} is followed by END (module doc: READY, DISPATCHED, RESULT, END). Nothing in the
        parent reads END; the marker file is evidence for whoever reads it, and is disposed with the evaluation."""
        run = self.start("app.calc:hang", "returns", 0.3)
        state, seen = self.until(run, "END")
        self.assertEqual(state, "LINE", seen)
        self.assertEqual(self.tags(), ["READY", "DISPATCHED", "RESULT", "END"])   # in this order, once each
        self.assertEqual(set(seen), {"READY", "DISPATCHED", "RESULT", "END"})   # each of them authentic
        self.assertEqual(json.loads(seen["RESULT"][0]), {"deadline": True})

    def test_the_controller_ends_by_itself_once_it_has_reported(self):
        """The window's timer must not keep the controller alive after the answers are in: with a window of ten
        minutes and a subject that answers at once, the process exits with status 0 and its protocol ends with END. A
        controller that lingers until the window ends is a range that is never empty for the whole window."""
        run = self.start("app.calc:add", "returns", 600, args=[1, 2])
        self.assertEqual(run.wait(20), 0)
        self.assertEqual(self.tags(), ["READY", "DISPATCHED", "RESULT", "END"])
        seen = ci._protocol(self.proto, self.nonce, self.key)
        self.assertEqual(set(seen), {"READY", "DISPATCHED", "RESULT", "END"})
        self.assertEqual(json.loads(seen["RESULT"][0]).get("returned"), 3)   # the call's answer, not a deadline


if __name__ == "__main__":
    unittest.main()
